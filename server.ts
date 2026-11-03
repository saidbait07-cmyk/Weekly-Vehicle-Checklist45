import http from 'node:http';
import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';

const PORT = Number(process.env.PORT || 3000);
const FLASK_PORT = Number(process.env.FLASK_RUN_PORT || 5000);
const ROOT = process.cwd();

let flaskProc: ChildProcess | null = null;
let flaskReady = false;
let isStartingFlask = false;

function buildPythonEnv(): NodeJS.ProcessEnv {
  const rawDbUrl = (process.env.DATABASE_URL || '').trim();
  const validDbPrefixes = ['sqlite://', 'postgresql://', 'postgresql+psycopg2://', 'postgres://', 'mysql://'];
  const safeDbUrl = validDbPrefixes.some((p) => rawDbUrl.startsWith(p))
    ? rawDbUrl
    : `sqlite:///${path.join(ROOT, 'fleet.db')}`;

  const rawTz = (process.env.APP_TIMEZONE || '').trim();
  const safeTz = rawTz && rawTz.includes('/') ? rawTz : 'Asia/Muscat';

  const homeDir = process.env.HOME || '/root';

  return {
    ...process.env,
    HOME: homeDir,
    DATABASE_URL: safeDbUrl,
    APP_TIMEZONE: safeTz,
    FLASK_RUN_PORT: String(FLASK_PORT),
    PYTHONUNBUFFERED: '1',
    PATH: `${homeDir}/.local/bin:/usr/local/bin:/usr/bin:/bin:${process.env.PATH || ''}`,
    PYTHONPATH: [
      `${homeDir}/.local/lib/python3.10/site-packages`,
      process.env.PYTHONPATH || '',
    ]
      .filter(Boolean)
      .join(':'),
  };
}

function runCommandAsync(cmd: string, args: string[], env: NodeJS.ProcessEnv): Promise<number> {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: ROOT,
      env,
      stdio: 'inherit',
    });
    child.on('error', () => resolve(1));
    child.on('close', (code) => resolve(code ?? 1));
  });
}

async function ensurePythonDependenciesAsync(env: NodeJS.ProcessEnv): Promise<void> {
  const checkCode = await runCommandAsync(
    'python3',
    ['-c', 'import flask, flask_sqlalchemy, openpyxl, qrcode, tzdata'],
    env
  );
  if (checkCode === 0) {
    return;
  }

  console.log('Bootstrapping Python packages asynchronously in /root/.local...');
  const pipCheck = await runCommandAsync('python3', ['-m', 'pip', '--version'], env);
  if (pipCheck !== 0) {
    await runCommandAsync(
      'sh',
      [
        '-c',
        'curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && python3 /tmp/get-pip.py --user --no-warn-script-location',
      ],
      env
    );
  }

  await runCommandAsync(
    'python3',
    [
      '-m',
      'pip',
      'install',
      '--user',
      '--no-warn-script-location',
      '-r',
      path.join(ROOT, 'requirements.txt'),
      'tzdata',
    ],
    env
  );
}

async function startFlaskServerAsync(): Promise<void> {
  if (isStartingFlask) return;
  isStartingFlask = true;

  try {
    const env = buildPythonEnv();
    await ensurePythonDependenciesAsync(env);

    flaskProc = spawn('python3', [path.join(ROOT, 'app.py')], {
      cwd: ROOT,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    flaskProc.stdout?.on('data', (chunk: Buffer) => {
      const text = chunk.toString();
      if (text.includes('Running on') || text.includes('Serving Flask app')) {
        flaskReady = true;
      }
    });

    flaskProc.stderr?.on('data', (chunk: Buffer) => {
      const text = chunk.toString();
      if (text.includes('Traceback') || text.includes('Error')) {
        console.error('[Flask]', text.trim());
      }
      if (text.includes('Running on') || text.includes('127.0.0.1')) {
        flaskReady = true;
      }
    });

    flaskProc.on('exit', (code) => {
      flaskReady = false;
      isStartingFlask = false;
      console.error(`Flask process exited with code ${code}; restarting in 1.5s...`);
      setTimeout(() => {
        startFlaskServerAsync().catch((err) => console.error(err));
      }, 1500);
    });
  } catch (err) {
    isStartingFlask = false;
    console.error('Failed to start Flask server:', err);
  }
}

function sendWarmupPage(clientRes: http.ServerResponse): void {
  clientRes.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
  });
  clientRes.end(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Smart Vehicle Inspection & Fleet Management System</title>
  <style>
    body { background: #071426; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .box { background: #0f2442; border: 1px solid #1e3a5f; border-radius: 12px; padding: 32px 36px; text-align: center; max-width: 420px; box-shadow: 0 18px 40px rgba(0,0,0,0.45); }
    .spinner { width: 34px; height: 34px; border: 3px solid rgba(59,130,246,0.25); border-top-color: #3b82f6; border-radius: 50%; margin: 0 auto 16px; animation: spin 0.8s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    h2 { margin: 0 0 8px; font-size: 18px; font-weight: 600; }
    p { margin: 0; color: #94a3b8; font-size: 14px; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="box">
    <div class="spinner"></div>
    <h2>Starting Fleet Inspection System</h2>
    <p>Initializing backend service, loading automatically in a moment…</p>
  </div>
  <script>
    async function pollReady() {
      try {
        const res = await fetch('/__health', { cache: 'no-store' });
        const data = await res.json();
        if (data && data.ready) {
          window.location.reload();
          return;
        }
      } catch (_) {}
      setTimeout(pollReady, 800);
    }
    setTimeout(pollReady, 800);
  </script>
</body>
</html>`);
}

function forwardToFlask(
  clientReq: http.IncomingMessage,
  clientRes: http.ServerResponse,
  bodyBuffer: Buffer,
  attempt = 0
): void {
  const rawForwardedHost =
    (clientReq.headers['x-forwarded-host'] as string) ||
    clientReq.headers.host ||
    `localhost:${PORT}`;
  const forwardedHost = rawForwardedHost.split(',')[0].trim();

  const originOrReferer = `${clientReq.headers.origin || ''} ${clientReq.headers.referer || ''}`;
  const isSecure =
    forwardedHost.includes('.run.app') ||
    (clientReq.headers['x-forwarded-proto'] as string)?.includes('https') ||
    originOrReferer.includes('https://');

  const headers: http.IncomingHttpHeaders = {
    ...clientReq.headers,
    host: forwardedHost,
    'x-forwarded-host': forwardedHost,
    'x-forwarded-proto': isSecure ? 'https' : 'http',
    'content-length': String(bodyBuffer.length),
    connection: 'close',
  };
  delete headers.upgrade;

  const proxyReq = http.request(
    {
      hostname: '127.0.0.1',
      port: FLASK_PORT,
      path: clientReq.url || '/',
      method: clientReq.method || 'GET',
      headers,
    },
    (proxyRes) => {
      flaskReady = true;
      const resHeaders: http.OutgoingHttpHeaders = { ...proxyRes.headers };
      if (typeof resHeaders.location === 'string') {
        resHeaders.location = resHeaders.location
          .replace(new RegExp(`^https?://127\\.0\\.0\\.1:${FLASK_PORT}`), '')
          .replace(new RegExp(`^https?://localhost:${PORT}`), '');
      }
      clientRes.writeHead(proxyRes.statusCode || 200, resHeaders);
      proxyRes.pipe(clientRes, { end: true });
    }
  );

  proxyReq.on('error', () => {
    if (attempt < 3) {
      setTimeout(() => {
        forwardToFlask(clientReq, clientRes, bodyBuffer, attempt + 1);
      }, 250);
      return;
    }
    sendWarmupPage(clientRes);
  });

  proxyReq.end(bodyBuffer);
}

async function main() {
  const server = http.createServer((clientReq, clientRes) => {
    if (clientReq.url === '/__health') {
      clientRes.writeHead(200, {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store',
      });
      clientRes.end(JSON.stringify({ ok: true, ready: flaskReady }));
      return;
    }

    const chunks: Buffer[] = [];
    clientReq.on('data', (chunk: Buffer) => chunks.push(chunk));
    clientReq.on('end', () => {
      const bodyBuffer = Buffer.concat(chunks);
      if (!flaskReady) {
        // Try connecting once quickly in case Flask just came up; otherwise return instant 200 warmup page
        forwardToFlask(clientReq, clientRes, bodyBuffer, 2);
        return;
      }
      forwardToFlask(clientReq, clientRes, bodyBuffer, 0);
    });
  });

  // Bind port 3000 synchronously and keep event loop 100% non-blocking
  server.listen(PORT, '0.0.0.0', () => {
    console.log(`Smart Vehicle Inspection & Fleet Management System listening on http://0.0.0.0:${PORT}`);
    startFlaskServerAsync().catch((err) => console.error(err));
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
