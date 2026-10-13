import re,html,sys
def show(f,kws,w=230,ctx=300,maxhits=1):
    t=open(f,encoding='utf-8',errors='replace').read()
    txt=re.sub(r'\s+',' ',html.unescape(re.sub(r'<script.*?</script>|<style.*?</style>','',t,flags=re.S)))
    print(f"===== {f} ({len(txt)} chars)")
    for kw in kws:
        hits=list(re.finditer(kw,txt,re.I))
        if not hits: print(f"  [{kw}] 0 hits"); continue
        for m in hits[:maxhits]:
            s=max(0,m.start()-w); print(f"  [{kw}] n={len(hits)} ...{txt[s:m.start()+ctx]}...")
if __name__=='__main__':
    f=sys.argv[1]; show(f,sys.argv[2:])
