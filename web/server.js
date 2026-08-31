// Stub server — replaced by the Next.js app in Phase 07 (recovery microsite) and Phase 11 (dashboard).
const http = require("http");

const port = process.env.PORT || 3000;

http
  .createServer((_req, res) => {
    res.writeHead(200, { "Content-Type": "text/plain" });
    res.end("recoup web — stub. The dashboard and recovery microsite land in Phase 07/11.\n");
  })
  .listen(port, () => {
    console.log(`recoup web stub listening on :${port}`);
  });
