import React from 'react';
import ReactDOM from 'react-dom/client';
import { DemoPage } from '../DemoPage';
import './index.css';
import '../../revisited.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <DemoPage />
  </React.StrictMode>
);
