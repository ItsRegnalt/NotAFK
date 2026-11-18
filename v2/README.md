# Automate V2 UI preview

This is a separate React preview based on the supplied UI code. Its start/stop,
coordinate picker, profile buttons, and telemetry are simulated in the browser;
it does not send mouse or keyboard input and does not use the Python automation
engine. The original desktop app remains available from the project root.

## Run

Install Node.js, then from this folder run:

```powershell
npm install
npm run dev -- --open
```

The page opens in your browser. Build a static preview with `npm run build`.
