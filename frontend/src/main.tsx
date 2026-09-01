import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import { UIProvider } from './context/UIContext';
import { ExamProvider } from './context/ExamContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <UIProvider>
        <ExamProvider>
          <App />
        </ExamProvider>
      </UIProvider>
    </BrowserRouter>
  </React.StrictMode>
);

