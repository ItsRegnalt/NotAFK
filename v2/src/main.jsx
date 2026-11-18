import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './style.css';

// Desktop shell = WebView2 (pywebview); the browser preview (npm run dev) has no bridge.
// 47823 = fixed port of the WebView2 shell's local server (ui/webview_shell.py HTTP_PORT).
if (location.port === '47823' || location.port === '47833') document.documentElement.classList.add('desktop'); // app / tests

const connectPywebview = () => {
  if (window.notafkBridge || !window.pywebview?.api?.startMacro) return;
  window.notafkBridge = window.pywebview.api;
  document.documentElement.classList.add('desktop');
  window.dispatchEvent(new Event('notafk:ready'));
};
window.addEventListener('pywebviewready', connectPywebview);
connectPywebview();

// The layout is designed for 1280x880; on smaller windows (laptops, 125-150% scaling) scale it down to fit.
const fit = () => {
  document.documentElement.style.setProperty('--fit', String(Math.min(1, innerWidth / 1280, innerHeight / 880)));
};
fit();
window.addEventListener('resize', fit);

let resizeTimer;
window.addEventListener('resize', () => {
  document.documentElement.classList.add('resizing');
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => document.documentElement.classList.remove('resizing'), 200);
});

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
