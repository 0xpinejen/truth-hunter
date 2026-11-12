/** Turn the composer input into the message actually submitted for investigation. */
export function composeInvestigationMessage(text: string, inputType = 'text'): {ok: true; message: string} | {ok: false; error: string} {
  const trimmed = String(text || '').trim();
  if (inputType !== 'url') return {ok: true, message: trimmed};
  try {
    const url = new URL(trimmed);
    if (url.protocol !== 'https:' || url.username || url.password) {
      return {ok: false, error: '请粘贴不含账号密码的 https 公开网页地址。'};
    }
    url.hash = '';
    return {ok: true, message: `请核查该公开网页中的具体说法：${url.href}`};
  } catch {
    return {ok: false, error: '网址模式需要完整的 https 链接，也可以改用「粘贴文字」。'};
  }
}
