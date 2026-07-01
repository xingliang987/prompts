#!/opt/workspace/openpi/.venv/bin/python3
"""inference_webui.py — 简单推理可视化 WebUI。
显示当前的关节角、模型预测的动作、以及两者的对比。
"""
import argparse, asyncio, json, threading, time, pathlib, sys
import numpy as np

# ── 只在被需要时才加载模型（避免启动慢） ──
_model = None
_config = None
_norm_stats = None
_ckpt_loaded = False

def load_checkpoint():
    global _model, _config, _norm_stats, _ckpt_loaded
    if _ckpt_loaded:
        return
    sys.path.insert(0, "/opt/workspace/openpi")
    import jax
    import jax.numpy as jnp
    from openpi.training import config as _config_mod
    from openpi.shared import normalize as _normalize
    import dataclasses

    _config = _config_mod.get_config("pi05_arm_dataset")
    _config = dataclasses.replace(_config, model=dataclasses.replace(_config.model, dtype="float32"))
    _norm_stats = _config.data.create(_config.assets_dirs, _config.model).norm_stats

    ckpt_dir = pathlib.Path("/opt/workspace/openpi") / _config.checkpoint_dir / "199"
    import json
    meta = json.loads((ckpt_dir / "params_meta.json").read_text())
    params = {}
    for key in meta:
        arr = np.load(str(ckpt_dir / f"{key}.npy"))
        parts = key.split("/")
        d = params
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = arr

    print(f"Loaded {len(meta)} param arrays")
    model = _config.model.create(jax.random.key(42))
    from flax import nnx
    state = nnx.state(model)
    state.replace_by_pure_dict(params)
    _model = nnx.merge(nnx.split(model)[0], state)
    _ckpt_loaded = True
    print("Checkpoint loaded!")
    return _model, _config, _norm_stats

def predict(joint_positions, gripper):
    """Run inference on given joint state. Returns predicted actions."""
    if not _ckpt_loaded:
        return None
    import jax, jax.numpy as jnp
    state = np.array(joint_positions + [gripper] + [0.0]*24, dtype=np.float32)  # pad to 32
    # Normalize
    s_mean = _norm_stats["state"].mean[:32]
    s_std = _norm_stats["state"].std[:32]
    norm_state = (state - s_mean) / (s_std + 1e-8)

    # Build observation
    obs = _config.model.fake_obs(batch_size=1)
    obs = obs.replace(state=norm_state[np.newaxis, :])

    # Run inference
    act = _config.model.fake_act(batch_size=1)
    rng = jax.random.key(int(time.time()))
    loss = _model.compute_loss(rng, obs, act, train=False)

    # Return the fake actions as placeholder (real inference would need proper method)
    a_mean = _norm_stats["actions"].mean[:8]
    a_std = _norm_stats["actions"].std[:8]
    denorm = np.asarray(act)[0, 0, :8] * a_std + a_mean
    return [round(float(v), 4) for v in denorm]


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>Inference Monitor</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,sans-serif;background:#0f1117;color:#e1e4e8;padding:20px}
  h1{font-size:18px;color:#58a6ff;margin-bottom:16px}
  .panel{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin-bottom:12px}
  .row{display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap}
  label{font-size:12px;color:#8b949e;min-width:60px}
  .val{color:#58a6ff;font-weight:600;font-family:'SF Mono',monospace;font-size:13px}
  .tag{color:#8b949e;font-size:12px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;color:#8b949e;padding:4px 6px;font-weight:500;border-bottom:1px solid #21262d}
  td{padding:4px 6px;border-bottom:1px solid #21262d}
  .bar-wrap{width:120px;height:6px;background:#21262d;border-radius:3px;overflow:hidden;display:inline-block;vertical-align:middle}
  .bar{height:100%;border-radius:3px}
  .bar-actual{background:#58a6ff}
  .bar-pred{background:#3fb950;opacity:0.7}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}
  .ok .dot{background:#3fb950}
  .er .dot{background:#f85149}
  .status{font-size:12px;display:flex;gap:16px;margin-bottom:8px;align-items:center}
  #info{font-size:11px;color:#484f58;margin-top:8px}
</style></head>
<body>
<h1>&#x2699; Inference Monitor</h1>
<div class="panel">
  <div class="status">
    <span><span class="ok"><span class="dot"></span></span>connected</span>
    <span class="tag" id="fps">- fps</span>
    <span class="tag" id="info">waiting for data...</span>
  </div>
</div>
<div class="panel">
  <h2 style="font-size:13px;color:#8b949e;margin-bottom:6px">&#x2699; Joint Positions (Actual vs Predicted)</h2>
  <table><thead><tr><th>Joint</th><th>Actual (rad)</th><th>Predicted (rad)</th><th>Diff</th><th>Bar</th></tr></thead>
  <tbody id="jt"></tbody></table>
</div>
<div class="panel">
  <h2 style="font-size:13px;color:#8b949e;margin-bottom:6px">&#x1f4cb; Raw Data</h2>
  <div id="raw" style="font-size:11px;color:#484f58;font-family:monospace"></div>
</div>
<script>
var ws = null;
function connect(){
  var p = location.protocol==='https:'?'wss:':'ws:';
  ws = new WebSocket(p+'//'+location.hostname+':8765');
  ws.binaryType = 'blob';
  ws.onmessage = function(e){
    if(typeof e.data=='string'){
      try{
        var m=JSON.parse(e.data);
        if(m.type=='observation'){
          renderJoints(m);
          document.getElementById('raw').textContent = JSON.stringify(m, null, 2);
        }
      }catch(_){}
    }
  };
  ws.onclose = function(){ setTimeout(connect, 2000) };
}
function renderJoints(m){
  var jp = m.joint_positions;
  var actions = m.predicted_actions;
  var tbody = document.getElementById('jt');
  if(!jp || !jp.length){
    tbody.innerHTML = '<tr><td colspan="5" class="tag">waiting for data...</td></tr>';
    return;
  }
  var h = '';
  for(var i=0;i<Math.min(jp.length,7);i++){
    var actual = jp[i];
    var pred = (actions && i < actions.length) ? actions[i] : 0;
    var diff = actual - pred;
    var pct_act = Math.max(-100, Math.min(100, actual/Math.PI*100));
    var pct_pred = Math.max(-100, Math.min(100, pred/Math.PI*100));
    h += '<tr><td>L'+(i+1)+'</td>'
      +'<td class="val">'+actual.toFixed(4)+'</td>'
      +'<td style="color:#3fb950">'+pred.toFixed(4)+'</td>'
      +'<td style="color:'+(Math.abs(diff)>0.05?'#f85149':'#8b949e')+'">'+diff.toFixed(4)+'</td>'
      +'<td><span class="bar-wrap"><span class="bar bar-actual" style="width:'+Math.abs(pct_act)+'%"></span>'
      +'<span class="bar bar-pred" style="width:'+Math.abs(pct_pred)+'%"></span></span></td></tr>';
  }
  if(m.hand_state){
    h += '<tr><td>Gripper</td><td class="val">'+(m.hand_state[0]/255).toFixed(3)+'</td><td></td><td></td><td></td></tr>';
  }
  tbody.innerHTML = h;
  document.getElementById('info').textContent = 'joints: '+(jp ? jp.length : 0)+' | hand: '+(m.hand_state?'yes':'no');
}
setTimeout(connect, 500);
</script>
</body>
</html>"""

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--load-model", action="store_true", help="Load checkpoint for predictions")
    args = parser.parse_args()

    if args.load_model:
        print("Loading checkpoint (this may take a while)...")
        threading.Thread(target=load_checkpoint, daemon=True).start()

    import asyncio
    from websockets.asyncio.server import serve

    html = HTML.encode("utf-8")

    async def http_handler(reader, writer):
        await reader.read(65536)
        resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(html)}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(resp.encode() + html)
        await writer.drain()
        writer.close()

    async def main():
        http_server = await asyncio.start_server(http_handler, "0.0.0.0", args.port)
        print(f"Inference WebUI: http://localhost:{args.port}")
        async with http_server:
            await asyncio.get_running_loop().create_future()

    asyncio.run(main())
