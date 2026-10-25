import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Integer, Text, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

def now():
    return datetime.now(timezone.utc).isoformat()

class Base(DeclarativeBase): pass

class Investigation(Base):
    __tablename__ = 'investigations'
    id = Column(String, primary_key=True)
    status = Column(String, nullable=False)
    payload = Column(Text, nullable=False)

class Record(Base):
    __tablename__ = 'records'
    id = Column(String, primary_key=True)
    investigation_id = Column(String, ForeignKey('investigations.id'), nullable=False, index=True)
    kind = Column(String, nullable=False)
    payload = Column(Text, nullable=False)

class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String, ForeignKey('investigations.id'), nullable=False, index=True)
    payload = Column(Text, nullable=False)

class Store:
    def __init__(self, url):
        if url.startswith('sqlite:///') and ':memory:' not in url:
            Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def create(self, id, payload):
        with self.session.begin() as s:
            s.add(Investigation(id=id, status='CREATED', payload=json.dumps(payload, ensure_ascii=False)))

    def get(self, id):
        with self.session() as s:
            row = s.get(Investigation, id)
            return dict(json.loads(row.payload), id=id, status=row.status) if row else None

    def list(self):
        with self.session() as s:
            return sorted([dict(json.loads(x.payload), id=x.id, status=x.status) for x in s.scalars(select(Investigation)).all()],key=lambda x:(x.get('created_at',''),x['id']),reverse=True)

    def emit(self, id, status, message, **details):
        from .contracts import TERMINAL
        with self.session.begin() as s:
            row = s.get(Investigation, id)
            if row.status in TERMINAL:
                return
            row.status = status
            s.add(Event(investigation_id=id, payload=json.dumps({'status':status,'message':message,'created_at':now(),**details}, ensure_ascii=False)))

    def put(self, id, kind, payload, record_id):
        with self.session.begin() as s:
            s.add(Record(id=record_id, investigation_id=id, kind=kind, payload=json.dumps(payload, ensure_ascii=False)))

    def records(self, id, kind=None):
        with self.session() as s:
            q = select(Record).where(Record.investigation_id == id)
            if kind: q = q.where(Record.kind == kind)
            return [dict(json.loads(x.payload),id=x.id,kind=x.kind) for x in s.scalars(q).all()]

    def events(self, id, after=0):
        with self.session() as s:
            return [dict(json.loads(x.payload), id=x.id) for x in s.scalars(select(Event).where(Event.investigation_id==id, Event.id>after).order_by(Event.id)).all()]

    def complete_review(self,id,base_report_id,review_id,review,report_id,report):
        from .providers import ProviderError
        with self.session.begin() as s:
            row=s.get(Investigation,id)
            reports=s.scalars(select(Record).where(Record.investigation_id==id,Record.kind=='report')).all()
            latest=max(reports,key=lambda r:json.loads(r.payload).get('revision',1)) if reports else None
            if row.status not in {'PARTIAL','COMPLETED'} or not latest or latest.id!=base_report_id:
                raise ProviderError('REVIEW_STALE_OR_NOT_READY')
            s.add(Record(id=review_id,investigation_id=id,kind='review',payload=json.dumps(review,ensure_ascii=False)))
            s.add(Record(id=report_id,investigation_id=id,kind='report',payload=json.dumps(report,ensure_ascii=False)))
            row.status='COMPLETED'
            s.add(Event(investigation_id=id,payload=json.dumps({'status':'COMPLETED','message':'显式复核完成，裁决及范围已留档；不保证所有声明都有定论。','created_at':now(),'review_id':review_id,'report_id':report_id},ensure_ascii=False)))
