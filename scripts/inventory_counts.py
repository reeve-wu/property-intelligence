import sys, zipfile, io, glob, os, collections
def walk(z):
    for n in z.namelist():
        if n.lower().endswith('.zip'):
            yield from walk(zipfile.ZipFile(io.BytesIO(z.read(n))))
        elif n.upper().endswith('.DAT'):
            yield n, z.read(n)
tot=0; raw=0
for p in sorted(glob.glob('' + sys.argv[1] + '/*.zip')):
    b=0; sz=0; arch=0; mind='99999999'; maxd='0'
    for n,data in walk(zipfile.ZipFile(p)):
        sz+=len(data)
        for l in data.decode('latin-1').splitlines():
            if l.startswith('B;'):
                f=l.split(';'); b+=1
                if len(f)==22: arch+=1; d=f[10]; d=d[6:]+d[3:5]+d[:2] if len(d)==10 else ''
                else: d=f[14]
                if d and d.isdigit(): mind=min(mind,d); maxd=max(maxd,d)
    tot+=b; raw+=sz
    print(os.path.basename(p), b, 'archive' if arch else 'current', f'{sz/1e6:.1f}MB', 'settle', mind, maxd)
print('TOTAL B', tot, f'{raw/1e9:.2f}GB uncompressed')
