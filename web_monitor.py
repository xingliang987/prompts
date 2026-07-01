#!/usr/bin/env python3
"""web_monitor.py — 机器人实时监控 Web 界面

启动方式:
  export ROBOT_HOST=192.168.127.66
  python3 web_monitor.py [--robot-port 8765] [--web-port 8080]

浏览器打开 http://<本机IP>:8080

浏览器通过 WebSocket 直连 robot_server，本脚本只负责提供 HTML 页面。
"""
import argparse
import asyncio
import os


HTML_TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Robot Monitor</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,'Segoe UI',sans-serif;background:#0f1117;color:#e1e4e8;padding:20px}
  h1{font-size:20px;margin-bottom:16px;color:#58a6ff}
  h2{font-size:14px;color:#8b949e;margin:12px 0 8px}
  .s{display:flex;gap:16px;margin-bottom:16px;font-size:13px;align-items:center}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
  .ok .dot{background:#3fb950}
  .er .dot{background:#f85149}
  .c{display:flex;gap:12px;margin-bottom:12px}
  .cb{flex:1;background:#161b22;border-radius:8px;padding:8px;border:1px solid #30363d}
  .cb img{width:100%;border-radius:4px;display:block;background:#0d1117}
  .cb .l{font-size:11px;color:#8b949e;margin-top:4px;text-align:center}
  table{width:100%;border-collapse:collapse;font-size:13px;background:#161b22;border-radius:8px;border:1px solid #30363d}
  th{text-align:left;color:#8b949e;padding:6px 10px;border-bottom:1px solid #30363d;font-weight:500}
  td{padding:6px 10px;border-bottom:1px solid #21262d}
  .v{text-align:right;font-family:'SF Mono',Monaco,monospace}
  .b{width:100px;height:6px;background:#21262d;border-radius:3px;overflow:hidden}
  .bf{height:100%;border-radius:3px;transition:width .1s}
  .bn{background:#f0883e}
  .bp{background:#58a6ff}
  .na{color:#484f58;text-align:center;padding:30px;font-size:13px}
  td:last-child{width:110px}
</style>
</head>
<body>
<h1>&#x1f916; Robot Monitor</h1>
<div class="s">
  <span id="co" class="er"><span class="dot"></span><span id="st">disconnected</span></span>
  <span id="fps">&#x23f1; - fps</span>
  <span style="color:#8b949e;font-size:12px" id="addr"></span>
</div>
<div class="c">
  <div class="cb"><img id="fcam"><div class="l">Front (335L)</div></div>
  <div class="cb"><img id="wcam"><div class="l">Wrist (305)</div></div>
</div>
<h2>&#x2699; Joint Positions</h2>
<table><thead><tr><th>Joint</th><th class="v">rad</th><th></th></tr></thead>
<tbody id="jt"><tr><td colspan="3" class="na">waiting for data...</td></tr></tbody></table>
<h2>&#x1f91e; Hand State</h2>
<div id="hs" style="font-size:13px;background:#161b22;border-radius:8px;padding:8px 10px;border:1px solid #30363d;color:#8b949e">waiting for data...</div>
<script>
var PF=0,PW=0,FC=0,LT=performance.now();
var WS=new WebSocket('ws://__HOST__:__PORT__');
WS.binaryType='blob';
var co=document.getElementById('co'),st=document.getElementById('st');
var fps=document.getElementById('fps'),jt=document.getElementById('jt');
var fc=document.getElementById('fcam'),wc=document.getElementById('wcam'),hs=document.getElementById('hs');
WS.onopen=function(){co.className='ok';st.textContent='connected'};
WS.onclose=function(){co.className='er';st.textContent='disconnected'};
WS.onerror=function(){co.className='er';st.textContent='error'};
WS.onmessage=function(e){
  if(typeof e.data=='string'){
    try{
      var m=JSON.parse(e.data);
      if(m.type=='observation'){
        if(m.joint_positions) renderJoints(m.joint_positions);
        if(m.hand_state) renderHandState(m.hand_state);
        PF=m.has_front_image?1:0;PW=m.has_wrist_image?1:0;
      }
    }catch(_){}
  }else{
    var u=URL.createObjectURL(e.data);
    if(PF){fc.onload=function(){URL.revokeObjectURL(u)};fc.src=u;PF=0}
    else if(PW){wc.onload=function(){URL.revokeObjectURL(u)};wc.src=u;PW=0}
  }
  FC++;var n=performance.now(),dt=n-LT;
  if(dt>1000){fps.textContent='⏱ '+(FC*1e3/dt|0)+' fps';FC=0;LT=n}
};
setInterval(function(){
  if(WS.readyState==1)WS.send(JSON.stringify({type:'get_observation'}))
},100);
function renderJoints(p){
  var h='',i;
  for(i=0;i<p.length;i++){
    var w=Math.max(-100,Math.min(100,p[i]/Math.PI*100));
    h+='<tr><td>L'+(i+1)+'</td><td class="v">'+p[i].toFixed(4)+'</td>'
      +'<td><div class="b"><div class="bf '+(p[i]>=0?'bp':'bn')+'" style="width:'+Math.abs(w)+'%"></div></div></td></tr>';
  }
  jt.innerHTML=h;
}
function renderHandState(s){
  hs.innerHTML='<span style="color:#e1e4e8">['+s.join(', ')+']</span> <span style="color:#8b949e">(0=closed, 255=open)</span>';
}
</script>
</body>
</html>"""


async def handle_http(reader, writer):
    """Serve the HTML page."""
    data = await reader.read(65536)
    request = data.decode("utf-8", errors="replace")
    if request.startswith("GET"):
        html = HTML_TPL.replace("__HOST__", ROBOT_HOST).replace("__PORT__", str(ROBOT_PORT))
        body = html.encode("utf-8")
        resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        writer.write(resp.encode("utf-8") + body)
    else:
        writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
    await writer.drain()
    writer.close()


async def main():
    parser = argparse.ArgumentParser(description="Robot Web Monitor")
    parser.add_argument("--robot-host", default=os.environ.get("ROBOT_HOST", "192.168.127.66"), help="robot_server IP")
    parser.add_argument("--robot-port", type=int, default=8765, help="robot_server port")
    parser.add_argument("--web-port", type=int, default=8080, help="web UI port")
    args = parser.parse_args()

    global ROBOT_HOST, ROBOT_PORT
    ROBOT_HOST = args.robot_host
    ROBOT_PORT = args.robot_port

    server = await asyncio.start_server(handle_http, "0.0.0.0", args.web_port)

    print(f"\n  Robot Monitor started!")
    print(f"  Open: http://localhost:{args.web_port}")
    print(f"  Robot: {args.robot_host}:{args.robot_port}")
    print(f"  Press Ctrl+C to stop\n")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
