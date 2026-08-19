import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import { installDesktopPageGuards } from './lib/desktopGuards';
import './index.css';

installDesktopPageGuards();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
