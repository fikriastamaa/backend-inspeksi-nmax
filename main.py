from contextlib import contextmanager
from pathlib import Path
import json, math, sqlite3, os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB = Path(__file__).resolve().parent / 'nmex.sqlite3'
app = FastAPI(title='NMEX API')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:5173','http://127.0.0.1:5173','https://inspeksi.fikriastama.com'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

DEFAULT_WEIGHTS = {'harga':20,'tahun':10,'kilometer':10,'pajak':5,'kondisi':10,'mesin_group':15,'fisik_group':10,'keselamatan_group':15,'dokumen_group':5}

SCORE_MAP = {
    'mesin':     {'Halus Sekali':5,'Halus':4,'Lumayan':3,'Agak Kasar':2,'Kasar':1},
    'cvt':       {'Normal':5,'Sedikit Berisik':3,'Selip':2,'Berisik':1},
    'bodi':      {'Mulus':5,'Baret Halus':4,'Baret':3,'Penyok Kecil':2,'Penyok/Retak':1},
    'suspensi':  {'Empuk Normal':5,'Sedikit Keras':4,'Keras':3,'Ada Bunyi':2,'Bermasalah':1},
    'ban':       {'Tebal':5,'Cukup':3,'Tipis':2,'Gundul':1},
    'rem':       {'Pakem':5,'Cukup Pakem':4,'Kurang Pakem':3,'Perlu Servis':2,'Bermasalah':1},
    'komstir':   {'Kencang':5,'Sedikit Main':4,'Agak Goyang':3,'Goyang':2,'Perlu Ganti':1},
    'kelistrikan':{'Semua Hidup':5,'Minor Mati':3,'Ada yang Mati':2,'Bermasalah':1},
    'dokumen':   {'Lengkap':5,'STNK Saja':3,'BPKB Saja':2,'Tidak Ada':1},
}

SAMPLE = [
('AB 3537 XV','Dealer Second','Yamaha NMAX',2022,27500000,'Panjang',49842,'Jambidan Bantul','no minus mulus mesin, mulus exterior mantap',4,'Belum diperiksa'),
('AB 4444 VJ','Dealer Second','Yamaha NMAX',2020,25200000,'Panjang',42412,'Imogiri Barat','part ori ga ada, sudah di modif, rem nya nyangkut, sudah ada yang di skotlet, suara mesin sedikit kasar',2,'Belum diperiksa'),
('AB 2852 HR','Dealer Second','Yamaha NMAX',2023,28500000,'Panjang',29513,'Imogiri Barat','cat pudar dikit, suara mesin agak dikit nggerung',3,'Belum diperiksa'),
('AB 2582 ZO','Perorangan','Yamaha NMAX',2023,28500000,'Belum bayar',28257,'Jakal KM 12,5','mulus juga',4,'Belum diperiksa'),
('AB 4074 XA','Perorangan','Yamaha NMAX',2021,25000000,'Belum bayar',42892,'Jakal KM 22','Bekas laka, body kanan baret, bekas jatuh',1,'Belum diperiksa'),
('AB 5946 UL','Perorangan','Yamaha NMAX',2021,25700000,'Panjang',35000,'Giwangan','Pajak panjang tertib, Surat lengkap, kondisi mesin standart kering, body orisinil bagus utuh, cat masih bagus, ban tebal, kelistrikan hidup',5,'Belum diperiksa'),
('AB 2108 UI','Perorangan','Yamaha NMAX',2020,25000000,'Panjang',53000,'Jakal KM 10','motor bekas rentalan',2,'Belum diperiksa')]

@contextmanager
def conn():
    db=sqlite3.connect(DB)
    db.row_factory=sqlite3.Row
    try:
        yield db
        db.commit()
    finally: db.close()

def init():
    with conn() as db:
        db.execute('CREATE TABLE IF NOT EXISTS motors (id INTEGER PRIMARY KEY AUTOINCREMENT, plat TEXT NOT NULL, penjual TEXT NOT NULL, motor TEXT NOT NULL, tahun INTEGER NOT NULL, harga INTEGER NOT NULL, pajak TEXT NOT NULL, kilometer INTEGER NOT NULL, lokasi TEXT NOT NULL DEFAULT "", catatan TEXT NOT NULL DEFAULT "", kondisi INTEGER NOT NULL, inspeksi TEXT NOT NULL DEFAULT "Belum diperiksa", link TEXT NOT NULL DEFAULT "")')
        for col in ['link','mesin','cvt','bodi','suspensi','ban','rem','komstir','kelistrikan','dokumen']:
            try: db.execute(f'ALTER TABLE motors ADD COLUMN {col} TEXT NOT NULL DEFAULT ""')
            except: pass
        db.execute('CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        if db.execute('SELECT COUNT(*) FROM motors').fetchone()[0]==0 and not db.execute('SELECT 1 FROM settings WHERE name="initialized"').fetchone():
            db.executemany('INSERT INTO motors (plat,penjual,motor,tahun,harga,pajak,kilometer,lokasi,catatan,kondisi,inspeksi) VALUES (?,?,?,?,?,?,?,?,?,?,?)', SAMPLE)
            db.execute('INSERT INTO settings VALUES (?,?)',('initialized','true'))
        if not db.execute('SELECT 1 FROM settings WHERE name="weights"').fetchone():
            db.execute('INSERT INTO settings VALUES (?,?)',('weights',json.dumps(DEFAULT_WEIGHTS)))
init()

def group_score(m, fields):
    vals=[SCORE_MAP[f][m[f]] for f in fields if m.get(f,'') and m[f] in SCORE_MAP[f]]
    return sum(vals)/len(vals) if vals else 3.0

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post('/api/login')
def login(req: LoginRequest):
    valid_user = os.environ.get('APP_USERNAME','fikriaja')
    valid_pass = os.environ.get('APP_PASSWORD','2026gantinmax')
    if req.username != valid_user or req.password != valid_pass:
        raise HTTPException(401, 'Username atau password salah.')
    return {'ok': True}

class Motor(BaseModel):
    plat: str = Field(min_length=2,max_length=30)
    penjual: str = 'Perorangan'
    motor: str = 'Yamaha NMAX'
    tahun: int = Field(ge=1990,le=2100)
    harga: int = Field(gt=0)
    pajak: str = 'Belum diketahui'
    kilometer: int = Field(ge=0)
    lokasi: str = ''
    catatan: str = ''
    kondisi: int = Field(ge=1,le=5)
    inspeksi: str = 'Belum diperiksa'
    link: str = ''
    mesin: str = ''
    cvt: str = ''
    bodi: str = ''
    suspensi: str = ''
    ban: str = ''
    rem: str = ''
    komstir: str = ''
    kelistrikan: str = ''
    dokumen: str = ''

class Weights(BaseModel):
    harga: float=Field(ge=0)
    tahun: float=Field(ge=0)
    kilometer: float=Field(ge=0)
    pajak: float=Field(ge=0)
    kondisi: float=Field(ge=0)
    mesin_group: float=Field(ge=0)
    fisik_group: float=Field(ge=0)
    keselamatan_group: float=Field(ge=0)
    dokumen_group: float=Field(ge=0)

@app.get('/api/motors')
def motors():
    with conn() as db: return [dict(x) for x in db.execute('SELECT * FROM motors ORDER BY id DESC')]

@app.post('/api/motors',status_code=201)
def add_motor(m:Motor):
    fields=list(m.model_dump())
    with conn() as db:
        cur=db.execute(f'INSERT INTO motors ({",".join(fields)}) VALUES ({",".join("?" for _ in fields)})',tuple(getattr(m,k) for k in fields))
        return {'id':cur.lastrowid}

@app.put('/api/motors/{motor_id}')
def edit_motor(motor_id:int,m:Motor):
    fields=list(m.model_dump())
    with conn() as db:
        cur=db.execute(f'UPDATE motors SET {",".join(f"{k}=?" for k in fields)} WHERE id=?',tuple(getattr(m,k) for k in fields)+(motor_id,))
        if not cur.rowcount: raise HTTPException(404,'Motor tidak ditemukan')
    return {'ok':True}

@app.delete('/api/motors/{motor_id}')
def delete_motor(motor_id:int):
    with conn() as db:
        cur=db.execute('DELETE FROM motors WHERE id=?',(motor_id,))
        if not cur.rowcount: raise HTTPException(404,'Motor tidak ditemukan')
    return {'ok':True}

@app.get('/api/weights')
def get_weights():
    with conn() as db: w=json.loads(db.execute('SELECT value FROM settings WHERE name="weights"').fetchone()[0])
    for k,v in DEFAULT_WEIGHTS.items():
        if k not in w: w[k]=v
    return w

@app.put('/api/weights')
def save_weights(w:Weights):
    obj=w.model_dump()
    if sum(obj.values())<=0: raise HTTPException(422,'Minimal satu bobot harus positif')
    with conn() as db: db.execute('UPDATE settings SET value=? WHERE name="weights"',(json.dumps(obj),))
    return obj

@app.get('/api/ranking')
def ranking():
    with conn() as db:
        records=[dict(x) for x in db.execute('SELECT * FROM motors')]
        w=json.loads(db.execute('SELECT value FROM settings WHERE name="weights"').fetchone()[0])
    for k,v in DEFAULT_WEIGHTS.items():
        if k not in w: w[k]=v
    if len(records)<2: return {'rows':[],'message':'Tambahkan minimal dua motor untuk membandingkan.'}
    keys=['harga','tahun','kilometer','pajak','kondisi','mesin_group','fisik_group','keselamatan_group','dokumen_group']
    pajak_map={'Panjang':2,'Belum bayar':1,'Pendek':1,'Belum diketahui':1}
    def values(m): return [
        m['harga'], m['tahun'], m['kilometer'], pajak_map.get(m['pajak'],1), m['kondisi'],
        group_score(m,['mesin','cvt']),
        group_score(m,['bodi','suspensi','ban']),
        group_score(m,['rem','komstir','kelistrikan']),
        group_score(m,['dokumen']),
    ]
    n=len(keys)
    raw=[values(m) for m in records]
    norm=[math.sqrt(sum(r[j]**2 for r in raw)) or 1 for j in range(n)]
    total=sum(w.get(k,0) for k in keys)
    if total<=0: raise HTTPException(422,'Bobot total tidak boleh nol')
    matrix=[[raw[i][j]/norm[j]*w.get(keys[j],0)/total for j in range(n)] for i in range(len(records))]
    benefit=[False,True,False,True,True,True,True,True,True]
    best=[(max if benefit[j] else min)(row[j] for row in matrix) for j in range(n)]
    worst=[(min if benefit[j] else max)(row[j] for row in matrix) for j in range(n)]
    out=[]
    for i,m in enumerate(records):
        dp=math.dist(matrix[i],best); dm=math.dist(matrix[i],worst)
        score=dm/(dp+dm) if dp+dm else .5
        out.append({**m,'score':round(score,5)})
    out.sort(key=lambda x:x['score'],reverse=True)
    for i,m in enumerate(out,1): m['rank']=i
    return {'rows':out,'message':'Skor bersifat simulasi. Kondisi adalah estimasi dari catatan penjual, bukan inspeksi.'}
