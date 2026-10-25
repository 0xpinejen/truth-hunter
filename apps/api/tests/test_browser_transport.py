import httpx
import pytest
from truthhunter.browser import fetch_pinned,public_addresses
from truthhunter.providers import ProviderError

@pytest.mark.asyncio
async def test_pinned_transport_preserves_tls_identity_and_does_not_follow_redirects():
    seen=[]
    def transport(request):
        seen.append(request)
        return httpx.Response(302,headers={'location':'https://127.0.0.1/private','set-cookie':'ignored=secret'},content=b'controlled response')
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport),follow_redirects=False) as c:
        status,headers,body=await fetch_pinned(c,'https://public.example/a?q=1','public.example','93.184.216.34')
    assert status==302 and len(seen)==1
    assert str(seen[0].url)=='https://93.184.216.34/a?q=1'
    assert seen[0].headers['host']=='public.example'
    assert seen[0].extensions['sni_hostname']=='public.example'
    assert headers['location']=='https://127.0.0.1/private' and 'set-cookie' not in headers

@pytest.mark.asyncio
@pytest.mark.parametrize('address',['127.0.0.1','198.18.7.215','169.254.169.254','::1','10.0.0.1'])
async def test_pinned_transport_cannot_send_to_private_or_fake_ip(address):
    def forbidden(_):raise AssertionError('No unsafe request may leave the application')
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as c:
        with pytest.raises(ProviderError,match='BLOCKED'):await fetch_pinned(c,'https://public.example/a','public.example',address)

@pytest.mark.asyncio
async def test_pinned_transport_caps_decompressed_response_bytes():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*(4*1024*1024+1)))) as c:
        with pytest.raises(ProviderError,match='TOO_LARGE'):await fetch_pinned(c,'https://public.example/','public.example','93.184.216.34')

@pytest.mark.asyncio
async def test_doh_is_opt_in_and_rejects_any_nonpublic_answer(monkeypatch):
    monkeypatch.setenv('BROWSER_DNS_MODE','doh')
    original=httpx.AsyncClient
    def transport(request):
        assert request.url.host=='cloudflare-dns.com'
        return httpx.Response(200,json={'Status':0,'Answer':[{'type':1,'data':'93.184.216.34'},{'type':1,'data':'127.0.0.1'}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    with pytest.raises(ProviderError,match='DNS_BLOCKED'):await public_addresses('public.example')

@pytest.mark.asyncio
async def test_every_redirect_is_validated_and_pinned_before_fetch():
    from truthhunter.browser import fetch_guarded
    seen=[]
    async def resolve(host):return ['93.184.216.34' if host=='first.example' else '1.1.1.1']
    def transport(request):
        seen.append(request)
        if request.headers['host']=='first.example':return httpx.Response(301,headers={'location':'https://second.test/final'})
        return httpx.Response(200,content=b'actual controlled body')
    network=[]
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport),follow_redirects=False) as c:
        final,status,headers,body=await fetch_guarded(c,'https://first.example/start',{'first.example','second.test'},resolve,network)
    assert final=='https://second.test/final' and status==200 and len(network)==2
    assert str(seen[0].url)=='https://93.184.216.34/start' and str(seen[1].url)=='https://1.1.1.1/final'
    assert seen[1].extensions['sni_hostname']=='second.test' and seen[1].headers['host']=='second.test'

@pytest.mark.asyncio
@pytest.mark.parametrize('location',['https://127.0.0.1/private','http://first.example/plain','https://evil.test/','https://pass@first.example/'])
async def test_redirect_cannot_escape_allowlist_https_or_credentials(location):
    from truthhunter.browser import fetch_guarded
    seen=[]
    async def resolve(host):return ['93.184.216.34']
    def transport(request):seen.append(request);return httpx.Response(302,headers={'location':location})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport),follow_redirects=False) as c:
        with pytest.raises(ProviderError,match='BLOCKED'):await fetch_guarded(c,'https://first.example/',{'first.example'},resolve,[])
    assert len(seen)==1

@pytest.mark.asyncio
async def test_redirect_limit_is_bounded():
    from truthhunter.browser import fetch_guarded
    async def resolve(host):return ['93.184.216.34']
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(301,headers={'location':'/again'}))) as c:
        with pytest.raises(ProviderError,match='TOO_MANY_REDIRECTS'):await fetch_guarded(c,'https://first.example/',{'first.example'},resolve,[])

def test_unsafe_search_candidates_are_not_selected():
    from truthhunter.engine import candidate_is_allowed
    assert not candidate_is_allowed('https://pass@www.python.org/test',{'python.org'})
    assert not candidate_is_allowed('http://www.python.org/test',{'python.org'})
    assert not candidate_is_allowed('https://www.python.org:8443/test',{'python.org'})
    assert candidate_is_allowed('https://docs.python.org/test',{'python.org'})

@pytest.mark.asyncio
async def test_public_web_mode_still_rejects_reserved_addresses():
    from truthhunter.browser import validate_public_url
    from truthhunter.providers import ProviderError
    async def reserved(host):return ['127.0.0.1']
    with pytest.raises(ProviderError):await validate_public_url('https://localhost/',{'*'},reserved)
    async def public(host):return ['1.1.1.1']
    assert await validate_public_url('https://www.python.org/',{'*'},public)=='www.python.org'
    with pytest.raises(ProviderError):await validate_public_url('https://user:pass@www.python.org/',{'*'},public)
