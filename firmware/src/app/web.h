// web.h — the HTTP face of the mask.
//
// Two servers on purpose. An MJPEG stream is a response that never ends, and
// it occupies its connection -- and, in esp_http_server, a worker -- for as
// long as somebody is watching. Sharing one server with the UI means the page
// stops loading the moment anyone opens the stream. So the stream gets its
// own server on its own port, exactly as Espressif's own camera example does.
#pragma once

bool web_begin();
