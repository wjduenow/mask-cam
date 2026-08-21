#include "web.h"
#include "capture.h"
#include "recorder.h"
#include "detect.h"
#include "ota.h"
#include "../config.h"

#include <Arduino.h>
#include <WiFi.h>
#include <SD_MMC.h>
#include <esp_http_server.h>
#include <Update.h>
#include <esp_heap_caps.h>

#if defined(__has_include)
#  if __has_include("../secrets.h")
#    include "../secrets.h"
#  endif
#endif

static httpd_handle_t http_srv = nullptr;
static httpd_handle_t stream_srv = nullptr;
static volatile int stream_clients = 0;

static const char *BOUNDARY = "maskcamframe";

// --- the page --------------------------------------------------------------
// Self-contained: no CDN, no fonts, nothing to fetch. The mask may well be on
// a network with no route to the internet, and a control page that needs one
// is a control page that does not work.
static const char PAGE[] PROGMEM = R"HTML(<!doctype html>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>mask-cam</title>
<style>
:root{color-scheme:dark light}
body{margin:0;font:15px/1.5 system-ui,sans-serif;background:#15161a;color:#e8e8ea}
header{padding:12px 16px;border-bottom:1px solid #2c2e35;display:flex;gap:12px;align-items:center}
h1{font-size:15px;margin:0;font-weight:600;letter-spacing:.02em}
main{padding:16px;max-width:900px;margin:0 auto}
#view{width:100%;background:#000;border-radius:8px;display:block;aspect-ratio:4/3;object-fit:contain}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0}
button,select{font:inherit;padding:7px 13px;border-radius:7px;border:1px solid #3a3d46;
  background:#23252c;color:inherit;cursor:pointer}
button:hover{background:#2c2f38}
button.on{background:#b8352f;border-color:#d2453e;color:#fff}
label{font-size:13px;opacity:.75}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
td,th{text-align:left;padding:5px 8px;border-bottom:1px solid #24262d}
th{opacity:.6;font-weight:500}
a{color:#7fb2ff}
#stat{font-size:13px;opacity:.8;line-height:1.7;white-space:pre-wrap;font-family:ui-monospace,monospace}
.warn{color:#ffb454}.bad{color:#ff6b6b}
</style>
<header><h1>mask-cam</h1><span id=badge style="font-size:13px;opacity:.7"></span></header>
<main>
<img id=view alt="live view">
<div class=row>
  <button id=rec>● record</button>
  <button id=snap>save still</button>
  <label>size <select id=fs>
    <option value=5>QVGA 320</option><option value=8>VGA 640</option>
    <option value=9 selected>SVGA 800</option><option value=10>XGA 1024</option>
    <option value=11>HD 1280</option><option value=13>UXGA 1600</option>
    <option value=17>QXGA 2048</option></select></label>
  <label>quality <select id=q>
    <option value=8>high</option><option value=12 selected>normal</option>
    <option value=18>low</option><option value=26>tiny</option></select></label>
  <label>fps <select id=fps>
    <option value=2>2</option><option value=5>5</option>
    <option value=10 selected>10</option><option value=15>15</option>
    <option value=20>20</option></select></label>
  <label><input type=checkbox id=ring> ring — <b>deletes oldest</b> to make room</label>
  <label><input type=checkbox id=mot> motion</label>
  <label><input type=checkbox id=vf> flip ↕</label>
  <label><input type=checkbox id=hm> mirror ↔</label>
</div>
<details id=tune><summary style="cursor:pointer;font-size:13px;opacity:.7">motion tuning</summary>
<div class=row style="font-size:13px">
  <label>block Δ <input id=md type=number min=1 max=80 style="width:60px"></label>
  <label>min blocks <input id=mn type=number min=1 max=200 style="width:60px"></label>
  <label>global % <input id=mp type=number min=10 max=100 style="width:60px"></label>
  <label>rate Hz <input id=mh type=number min=1 max=10 style="width:60px"></label>
  <button id=mapply style="padding:4px 10px">apply</button>
  <span id=mlive style="opacity:.7"></span>
</div>
<div style="font-size:12px;opacity:.6;line-height:1.6;margin:4px 0 10px">
  Phase 1: motion is <b>logged only</b> — it never starts or stops recording, so a
  wrong threshold costs a wrong label, not footage. <b>block Δ</b> is how different an
  8×8 block must be to count as changed; <b>min blocks</b> how many must change;
  <b>global %</b> is the ceiling above which a change is treated as lighting rather
  than motion, and is the setting that keeps the AEC from tripping it.
</div>
</details>
<div id=stat></div>
<details id=fw><summary style="cursor:pointer;font-size:13px;opacity:.7">firmware</summary>
<div class=row style="font-size:13px">
  <input type=file id=fwfile accept=".bin">
  <input type=password id=fwkey placeholder="OTA password" style="width:150px;
    padding:6px 9px;border-radius:7px;border:1px solid #3a3d46;background:#23252c;color:inherit">
  <button id=fwgo>upload &amp; reboot</button>
</div>
<div class=row style="margin-top:0"><progress id=fwbar value=0 max=100
  style="width:100%;display:none"></progress></div>
<div id=fwmsg style="font-size:12px;opacity:.7;min-height:1.2em"></div>
<div style="font-size:12px;opacity:.6;line-height:1.6;margin:4px 0 10px">
  Upload <code>firmware/.pio/build/mask-cam/firmware.bin</code>. It is written to the
  <b>inactive</b> app slot and only becomes the running firmware once the whole image
  has arrived and verified — a failed upload leaves this one untouched. Recording
  stops and the clip is closed cleanly first. Over the wire this is plain HTTP on
  your own network, password and all.
</div>
</details>

<div class=row><strong style="font-size:13px">motion</strong>
  <button id=mrefresh style="padding:3px 9px;font-size:12px">refresh</button>
  <button id=mclear style="padding:3px 9px;font-size:12px">clear log</button></div>
<table id=mevents><tr><th>when<th>clip<th>at<th>blocks</tr></table>

<div class=row><strong style="font-size:13px">recordings</strong>
  <button id=refresh style="padding:3px 9px;font-size:12px">refresh</button></div>
<table id=files><tr><th>clip<th>size<th></tr></table>
</main>
<script>
const $=s=>document.querySelector(s);
$('#view').src='http://'+location.hostname+':81/stream';

const fmt=n=>n>1073741824?(n/1073741824).toFixed(2)+' GB'
  :n>1048576?(n/1048576).toFixed(1)+' MB':(n/1024).toFixed(0)+' kB';

async function poll(){
  try{
    const h=await (await fetch('/health')).json();
    $('#rec').className=h.armed?'on':'';
    $('#rec').textContent=h.armed?'■ stop':(h.paused?'● paused':'● record');
    $('#ring').checked=h.ring;
    const tc=h.temp_c>70?'bad':h.temp_c>60?'warn':'';
    $('#badge').innerHTML=h.sensor+' · '+h.w+'×'+h.h+' · '+h.fps.toFixed(1)+' fps'
      +' · <span class='+tc+'>'+h.temp_c.toFixed(0)+'°C</span>'
      +(h.ota_active?' · <b>OTA '+h.ota_pct+'%</b>':'');
    $('#stat').textContent=
      (h.armed?'recording  '+h.clip+'   '+h.clip_frames+' frames, '+fmt(h.clip_bytes)
             :'idle')+'\n'
      +'card       '+h.card_free_mb+' MB free of '+h.card_total_mb+' MB'
      +'   ('+h.clips+' clips written)\n'
      +'sd write   '+h.write_ms_last+' ms last, '+h.write_ms_max+' ms worst'
      +(h.dropped?'   '+h.dropped+' DROPPED':'')+'\n'
      +'memory     '+fmt(h.heap)+' heap, '+fmt(h.psram)+' psram free\n'
      +'uptime     '+Math.floor(h.uptime_s/3600)+'h '
                    +Math.floor(h.uptime_s%3600/60)+'m'
      +(h.error?'\nlast error '+h.error:'');
  }catch(e){ $('#stat').textContent='no reply from the mask'; }
}
async function files(){
  const l=await (await fetch('/files')).json();
  l.sort((a,b)=>b.name.localeCompare(a.name));
  $('#files').innerHTML='<tr><th>clip<th>size<th></tr>'+l.map(f=>
    '<tr><td><a href="/download?f='+f.name+'">'+f.name+'</a><td>'+fmt(f.size)
    +'<td><button data-d="'+f.name+'" style="padding:2px 8px;font-size:12px">delete</button>').join('');
  $('#files').querySelectorAll('[data-d]').forEach(b=>b.onclick=async()=>{
    if(confirm('Delete '+b.dataset.d+'?')){ await fetch('/delete?f='+b.dataset.d); files(); }});
}
$('#rec').onclick=async()=>{ const on=$('#rec').className!=='on';
  await fetch('/rec?on='+(on?1:0)); poll(); setTimeout(files,500); };
$('#snap').onclick=()=>window.open('/still','_blank');
$('#ring').onchange=()=>fetch('/config?ring='+($('#ring').checked?1:0));
$('#mot').onchange=()=>fetch('/config?mot='+($('#mot').checked?1:0));
// Both together is a 180 degree rotation, which is what an upside-down sensor
// needs. Only one of them leaves the picture mirrored.
const flip=()=>fetch('/config?vflip='+($('#vf').checked?1:0)
                    +'&hmirror='+($('#hm').checked?1:0));
$('#vf').onchange=flip; $('#hm').onchange=flip;
$('#mapply').onclick=async()=>{
  await fetch('/config?mot_diff='+$('#md').value+'&mot_min='+$('#mn').value
             +'&mot_pct='+$('#mp').value+'&mot_hz='+$('#mh').value);
  poll();
};
async function motion(){
  const l=await (await fetch('/motion?n=40')).json();
  $('#mevents').innerHTML='<tr><th>when<th>clip<th>at<th>blocks</tr>'+(l.length?l.map(e=>
    '<tr><td>'+e.t+'<td><a href="/download?f='+e.clip+'">'+e.clip.replace(/\.avi$/,'')+'</a>'
    +'<td>+'+e.into+'s<td>'+e.blocks+'/'+e.total).join('')
    :'<tr><td colspan=4 style="opacity:.5">no events yet</tr>');
}
$('#fwgo').onclick=()=>{
  const f=$('#fwfile').files[0];
  if(!f){ $('#fwmsg').textContent='pick a .bin first'; return; }
  const x=new XMLHttpRequest();
  x.open('POST','/update');
  if($('#fwkey').value) x.setRequestHeader('X-OTA-Key',$('#fwkey').value);
  $('#fwbar').style.display='block';
  x.upload.onprogress=e=>{ if(e.lengthComputable){
    $('#fwbar').value=100*e.loaded/e.total;
    $('#fwmsg').textContent='uploading '+Math.round(100*e.loaded/e.total)+'% of '+fmt(e.total); }};
  x.onload=()=>{ $('#fwmsg').textContent=x.responseText;
    if(x.status===200){ $('#fwmsg').textContent+='  — reconnecting in 15 s…';
      setTimeout(()=>location.reload(),15000); } };
  x.onerror=()=>{ $('#fwmsg').textContent='upload failed — the running firmware is untouched'; };
  x.send(f);
};
$('#mrefresh').onclick=motion;
$('#mclear').onclick=async()=>{ if(confirm('Clear the motion log?')){
  await fetch('/motion?clear=1'); motion(); }};
for(const [id,key] of [['fs','framesize'],['q','quality'],['fps','fps']])
  $('#'+id).onchange=e=>fetch('/config?'+key+'='+e.target.value);
$('#refresh').onclick=files;
let tuned=false;
const _poll=poll;
poll=async function(){ await _poll();
  try{ const h=await (await fetch('/health')).json();
    $('#mot').checked=h.mot;
    $('#vf').checked=!!h.vflip; $('#hm').checked=!!h.hmirror;
    $('#mlive').textContent='live: '+h.mot_blocks+'/'+h.mot_total+' blocks, '+h.mot_ms+' ms';
    if(!tuned){ $('#md').value=h.mot_diff; $('#mn').value=h.mot_min;
                $('#mp').value=h.mot_pct;  $('#mh').value=h.mot_hz; tuned=true; }
  }catch(e){}
};
poll(); files(); motion(); setInterval(poll,2000); setInterval(motion,15000);
</script>
)HTML";

// --- helpers ---------------------------------------------------------------

static bool query_int(httpd_req_t *r, const char *key, int *out) {
  size_t n = httpd_req_get_url_query_len(r) + 1;
  if (n <= 1) return false;
  char *q = (char *)malloc(n);
  if (!q) return false;
  bool got = false;
  if (httpd_req_get_url_query_str(r, q, n) == ESP_OK) {
    char val[16];
    if (httpd_query_key_value(q, key, val, sizeof(val)) == ESP_OK) {
      *out = atoi(val);
      got = true;
    }
  }
  free(q);
  return got;
}

static bool query_str(httpd_req_t *r, const char *key, char *out, size_t cap) {
  size_t n = httpd_req_get_url_query_len(r) + 1;
  if (n <= 1) return false;
  char *q = (char *)malloc(n);
  if (!q) return false;
  bool got = false;
  if (httpd_req_get_url_query_str(r, q, n) == ESP_OK)
    got = httpd_query_key_value(q, key, out, cap) == ESP_OK;
  free(q);
  return got;
}

static esp_err_t send_json(httpd_req_t *r, const String &s) {
  httpd_resp_set_type(r, "application/json");
  httpd_resp_set_hdr(r, "Cache-Control", "no-store");
  return httpd_resp_send(r, s.c_str(), s.length());
}

// --- handlers --------------------------------------------------------------

static esp_err_t h_index(httpd_req_t *r) {
  httpd_resp_set_type(r, "text/html");
  return httpd_resp_send(r, PAGE, strlen_P(PAGE));
}

static esp_err_t h_health(httpd_req_t *r) {
  CapStats c; capture_stats(&c);
  RecStats s; recorder_stats(&s);

  String j = "{";
  j += "\"sensor\":\"" + String(capture_sensor_name()) + "\"";
  j += ",\"w\":" + String(c.width) + ",\"h\":" + String(c.height);
  j += ",\"fps\":" + String(c.fps_actual, 1);
  j += ",\"fps_target\":" + String(c.fps_target);
  j += ",\"vflip\":" + String(c.vflip) + ",\"hmirror\":" + String(c.hmirror);
  j += ",\"frames\":" + String(c.frames) + ",\"cam_fails\":" + String(c.fails);
  j += ",\"armed\":" + String(s.armed ? "true" : "false");
  j += ",\"ring\":" + String(s.ring ? "true" : "false");
  j += ",\"clip\":\"" + String(s.clip) + "\"";
  j += ",\"clip_frames\":" + String(s.clip_frames);
  j += ",\"clip_bytes\":" + String((uint32_t)s.clip_bytes);
  j += ",\"clips\":" + String(s.clips_written);
  j += ",\"deleted\":" + String(s.clips_deleted);
  j += ",\"paused\":" + String(s.paused_for_space ? "true" : "false");
  j += ",\"dropped\":" + String(s.frames_dropped);
  j += ",\"queue\":" + String(s.queue_depth);
  j += ",\"write_ms_last\":" + String(s.write_ms_last);
  j += ",\"write_ms_max\":" + String(s.write_ms_max);
  j += ",\"card_total_mb\":" + String((uint32_t)s.card_total_mb);
  j += ",\"card_free_mb\":" + String((uint32_t)s.card_free_mb);
  j += ",\"heap\":" + String((uint32_t)ESP.getFreeHeap());
  j += ",\"psram\":" + String((uint32_t)ESP.getFreePsram());
  j += ",\"temp_c\":" + String(temperatureRead(), 1);
  j += ",\"rssi\":" + String(WiFi.RSSI());
  j += ",\"viewers\":" + String(stream_clients);
  MotStats m; motion_stats(&m);
  j += ",\"mot\":" + String(m.enabled ? "true" : "false");
  j += ",\"mot_checks\":" + String(m.checks);
  j += ",\"mot_events\":" + String(m.events);
  j += ",\"mot_rejected\":" + String(m.rejected_global);
  j += ",\"mot_blocks\":" + String(m.last_blocks);
  j += ",\"mot_total\":" + String(m.total_blocks);
  j += ",\"mot_ms\":" + String(m.last_decode_ms);
  j += ",\"mot_lum\":" + String(m.last_lum);
  j += ",\"mot_global\":" + String(m.last_global ? "true" : "false");
  j += ",\"mot_last\":\"" + String(m.last_event) + "\"";
  int bd, mb, gp, hz; motion_get_params(&bd, &mb, &gp, &hz);
  j += ",\"mot_diff\":" + String(bd) + ",\"mot_min\":" + String(mb);
  j += ",\"mot_pct\":" + String(gp) + ",\"mot_hz\":" + String(hz);
  OtaStats o; ota_stats(&o);
  j += ",\"fw_build\":\"" __DATE__ " " __TIME__ "\"";
  j += ",\"fw_part\":\"" + String(o.running_part) + "\"";
  j += ",\"ota_active\":" + String(o.active ? "true" : "false");
  j += ",\"ota_pct\":" + String(o.percent);
  j += ",\"ota_src\":\"" + String(o.source) + "\"";
  j += ",\"ota_err\":\"" + String(o.last_error) + "\"";
  j += ",\"ota_auth\":" + String(ota_password_required() ? "true" : "false");
  j += ",\"uptime_s\":" + String(millis() / 1000);
  j += ",\"error\":\"" + String(s.last_error) + "\"";
  return send_json(r, j + "}");
}

static esp_err_t h_still(httpd_req_t *r) {
  size_t cap = capture_max_frame_bytes();
  uint8_t *buf = (uint8_t *)ps_malloc(cap);
  if (!buf) { httpd_resp_send_500(r); return ESP_FAIL; }

  uint32_t seq = 0;
  size_t n = capture_wait_frame(buf, cap, &seq, 3000);
  if (!n) { free(buf); httpd_resp_send_500(r); return ESP_FAIL; }

  httpd_resp_set_type(r, "image/jpeg");
  httpd_resp_set_hdr(r, "Content-Disposition", "inline; filename=mask-cam.jpg");
  esp_err_t e = httpd_resp_send(r, (const char *)buf, n);
  free(buf);
  return e;
}

static esp_err_t h_rec(httpd_req_t *r) {
  int on = 0;
  if (query_int(r, "on", &on)) {
    if (on) recorder_arm(); else recorder_disarm();
  }
  return send_json(r, String("{\"armed\":") + (recorder_armed() ? "true" : "false") + "}");
}

static esp_err_t h_config(httpd_req_t *r) {
  int v;
  if (query_int(r, "framesize", &v)) capture_set_framesize((framesize_t)v);
  if (query_int(r, "quality", &v))   capture_set_quality(v);
  if (query_int(r, "fps", &v))       capture_set_fps(v);
  if (query_int(r, "ring", &v))      recorder_set_ring(v != 0);
  {
    CapStats c; capture_stats(&c);
    int vf = c.vflip, hm = c.hmirror, touched = 0;
    if (query_int(r, "vflip", &v))   { vf = v; touched = 1; }
    if (query_int(r, "hmirror", &v)) { hm = v; touched = 1; }
    if (touched) capture_set_flip(vf, hm);
  }
  if (query_int(r, "mot", &v))       motion_set_enabled(v != 0);
  {
    int bd, mb, gp, hz; motion_get_params(&bd, &mb, &gp, &hz);
    if (query_int(r, "mot_diff", &v)) bd = v;
    if (query_int(r, "mot_min", &v))  mb = v;
    if (query_int(r, "mot_pct", &v))  gp = v;
    if (query_int(r, "mot_hz", &v))   hz = v;
    motion_set_params(bd, mb, gp, hz);
  }
  return send_json(r, "{\"ok\":true}");
}

static esp_err_t h_files(httpd_req_t *r) { return send_json(r, recorder_list_json()); }

static esp_err_t h_motion(httpd_req_t *r) {
  int n = 40;
  query_int(r, "n", &n);
  if (n < 1) n = 1;
  if (n > 200) n = 200;
  int clear = 0;
  if (query_int(r, "clear", &clear) && clear) recorder_clear_motion_log();
  return send_json(r, recorder_motion_json(n));
}

static esp_err_t h_delete(httpd_req_t *r) {
  char name[64];
  bool ok = query_str(r, "f", name, sizeof(name)) && recorder_delete(name);
  return send_json(r, String("{\"ok\":") + (ok ? "true" : "false") + "}");
}

static esp_err_t h_download(httpd_req_t *r) {
  char name[64];
  if (!query_str(r, "f", name, sizeof(name)) ||
      strchr(name, '/') || strstr(name, "..")) {
    httpd_resp_send_err(r, HTTPD_400_BAD_REQUEST, "bad name");
    return ESP_FAIL;
  }
  char path[96];
  snprintf(path, sizeof(path), MC_REC_DIR "/%s", name);
  File f = SD_MMC.open(path, FILE_READ);
  if (!f || f.isDirectory()) {
    httpd_resp_send_err(r, HTTPD_404_NOT_FOUND, "no such clip");
    return ESP_FAIL;
  }

  httpd_resp_set_type(r, "video/x-msvideo");
  char disp[128];
  snprintf(disp, sizeof(disp), "attachment; filename=%s", name);
  httpd_resp_set_hdr(r, "Content-Disposition", disp);

  // Chunked out of a modest buffer: a clip is tens of megabytes and there is
  // nowhere to hold one.
  const size_t CH = 8192;
  uint8_t *buf = (uint8_t *)malloc(CH);
  if (!buf) { f.close(); httpd_resp_send_500(r); return ESP_FAIL; }
  esp_err_t e = ESP_OK;
  while (true) {
    size_t n = f.read(buf, CH);
    if (n == 0) break;
    if (httpd_resp_send_chunk(r, (const char *)buf, n) != ESP_OK) { e = ESP_FAIL; break; }
  }
  free(buf);
  f.close();
  httpd_resp_send_chunk(r, nullptr, 0);
  return e;
}

// --- firmware update over HTTP ---------------------------------------------
//
// The page POSTs the .bin as a RAW body rather than as multipart/form-data,
// which means no multipart parser on a device that has better things to do.
//
// Update writes to the INACTIVE app slot and only flips otadata once the whole
// image is in and its checksum verifies, so an upload that dies halfway leaves
// the running firmware exactly where it was. That is the property that makes
// this safe to expose on a device nobody can reach with a cable.

static esp_err_t h_update(httpd_req_t *r) {
#ifdef OTA_PASSWORD
  char key[80] = "";
  if (httpd_req_get_hdr_value_str(r, "X-OTA-Key", key, sizeof(key)) != ESP_OK ||
      strcmp(key, OTA_PASSWORD) != 0) {
    httpd_resp_set_status(r, "401 Unauthorized");
    const char *m = "wrong or missing OTA password";
    httpd_resp_send(r, m, strlen(m));
    return ESP_OK;
  }
#endif

  size_t total = r->content_len;
  // A truncated or empty POST must not be allowed to start an update: begin()
  // erases the target slot, and erasing it for a 12-byte body is pointless.
  if (total < 200000) {
    httpd_resp_set_status(r, "400 Bad Request");
    const char *m = "that is too small to be a firmware image";
    httpd_resp_send(r, m, strlen(m));
    return ESP_OK;
  }

  ota_prepare("web");

  if (!Update.begin(total)) {
    char msg[96];
    snprintf(msg, sizeof(msg), "Update.begin failed: %s", Update.errorString());
    ota_note_error(msg);
    ota_resume();
    httpd_resp_set_status(r, "500 Internal Server Error");
    httpd_resp_send(r, msg, strlen(msg));
    return ESP_OK;
  }

  uint8_t *buf = (uint8_t *)malloc(4096);
  if (!buf) { Update.abort(); ota_resume(); httpd_resp_send_500(r); return ESP_FAIL; }

  size_t got = 0;
  int stalls = 0;
  bool ok = true;
  while (got < total) {
    int n = httpd_req_recv(r, (char *)buf, (total - got) < 4096 ? (total - got) : 4096);
    if (n == HTTPD_SOCK_ERR_TIMEOUT) {
      // A weak link stalls; that is not a failure until it stays stalled.
      if (++stalls > 20) { ok = false; ota_note_error("upload stalled"); break; }
      continue;
    }
    if (n <= 0) { ok = false; ota_note_error("connection dropped mid-upload"); break; }
    stalls = 0;
    if ((int)Update.write(buf, n) != n) {
      ok = false;
      ota_note_error(Update.errorString());
      break;
    }
    got += n;
    ota_note_progress(got, total);
  }
  free(buf);

  // Careful with the message here. When the SOCKET dies, Update itself never
  // failed, so Update.errorString() cheerfully returns "No Error" -- and
  // reporting "update failed: No Error" to somebody whose mask is screwed to a
  // wall is worse than useless. The loop already recorded why it stopped; only
  // reach for Update's own reason when the transfer completed and end()
  // rejected the image.
  bool ended = ok && Update.end(true);
  if (!ended) {
    if (ok) {
      char msg[96];
      snprintf(msg, sizeof(msg), "image rejected: %s", Update.errorString());
      ota_note_error(msg);
    }
    Update.abort();
    ota_resume();

    OtaStats o; ota_stats(&o);
    httpd_resp_set_status(r, "500 Internal Server Error");
    char out[160];
    int n = snprintf(out, sizeof(out),
                     "%s -- the running firmware is untouched",
                     o.last_error[0] ? o.last_error : "update failed");
    httpd_resp_send(r, out, n);
    return ESP_OK;
  }

  const char *done = "ok -- image verified, rebooting into it";
  httpd_resp_send(r, done, strlen(done));
  Serial.println("[ota] web image verified -- rebooting into it");
  delay(800);                       // let the reply reach the browser
  ESP.restart();
  return ESP_OK;
}

// --- the stream ------------------------------------------------------------

static esp_err_t h_stream(httpd_req_t *r) {
  if (stream_clients >= MC_MAX_STREAM_CLIENTS) {
    // This IDF's error enum has no 503, so set the status line by hand rather
    // than telling a viewer the mask is broken when it is merely busy.
    httpd_resp_set_status(r, "503 Service Unavailable");
    httpd_resp_set_type(r, "text/plain");
    const char *msg = "mask-cam: too many viewers already watching";
    httpd_resp_send(r, msg, strlen(msg));
    return ESP_OK;
  }

  size_t cap = capture_max_frame_bytes();
  uint8_t *buf = (uint8_t *)ps_malloc(cap);
  if (!buf) { httpd_resp_send_500(r); return ESP_FAIL; }

  char ct[64];
  snprintf(ct, sizeof(ct), "multipart/x-mixed-replace;boundary=%s", BOUNDARY);
  httpd_resp_set_type(r, ct);
  httpd_resp_set_hdr(r, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(r, "Cache-Control", "no-store");

  stream_clients++;
  uint32_t seq = 0;
  esp_err_t e = ESP_OK;
  char part[128];

  while (e == ESP_OK) {
    size_t n = capture_wait_frame(buf, cap, &seq, 5000);
    if (!n) continue;                       // pump hiccup: keep the socket open

    int len = snprintf(part, sizeof(part),
                       "\r\n--%s\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
                       BOUNDARY, (unsigned)n);
    e = httpd_resp_send_chunk(r, part, len);
    if (e == ESP_OK) e = httpd_resp_send_chunk(r, (const char *)buf, n);
  }

  stream_clients--;
  free(buf);
  return e;
}

// --- wiring ----------------------------------------------------------------

static void reg(httpd_handle_t s, const char *uri, esp_err_t (*fn)(httpd_req_t *)) {
  httpd_uri_t u = { .uri = uri, .method = HTTP_GET, .handler = fn, .user_ctx = nullptr };
  httpd_register_uri_handler(s, &u);
}

bool web_begin() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port      = MC_HTTP_PORT;
  cfg.ctrl_port        = 32768;
  cfg.max_uri_handlers = 12;
  cfg.lru_purge_enable = true;
  cfg.stack_size       = 8192;             // the SD read path runs on this task
  // A firmware image is ~1 MB over a link that has measured 25 kB/s at its
  // worst. The default 5 s recv timeout would abandon the upload; the handler
  // tolerates timeouts on top of this and only gives up after twenty in a row.
  cfg.recv_wait_timeout = 15;
  cfg.send_wait_timeout = 15;
  if (httpd_start(&http_srv, &cfg) != ESP_OK) return false;

  reg(http_srv, "/",         h_index);
  reg(http_srv, "/health",   h_health);
  reg(http_srv, "/still",    h_still);
  reg(http_srv, "/rec",      h_rec);
  reg(http_srv, "/config",   h_config);
  reg(http_srv, "/files",    h_files);
  reg(http_srv, "/motion",   h_motion);
  {
    httpd_uri_t u = { .uri = "/update", .method = HTTP_POST,
                      .handler = h_update, .user_ctx = nullptr };
    httpd_register_uri_handler(http_srv, &u);
  }
  reg(http_srv, "/delete",   h_delete);
  reg(http_srv, "/download", h_download);

  httpd_config_t scfg = HTTPD_DEFAULT_CONFIG();
  scfg.server_port      = MC_STREAM_PORT;
  scfg.ctrl_port        = 32769;
  scfg.max_open_sockets = MC_MAX_STREAM_CLIENTS + 1;
  scfg.lru_purge_enable = true;
  if (httpd_start(&stream_srv, &scfg) != ESP_OK) return false;
  reg(stream_srv, "/stream", h_stream);

  Serial.printf("[web] http://%s:%d/  stream on :%d\n",
                WiFi.localIP().toString().c_str(), MC_HTTP_PORT, MC_STREAM_PORT);
  return true;
}
