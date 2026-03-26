import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import SupportPage from './SupportPage.tsx'
import SupportAdminPage from './SupportAdminPage.tsx'
import SupportFloatingButton from './SupportFloatingButton.tsx'

const path = window.location.pathname.replace(/\/+$/, "") || "/";

const resolvePage = () => {
  if (path === "/support") return <SupportPage />;
  if (path === "/support/admin") return <SupportAdminPage />;
  return <App />;
};

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <>
      {resolvePage()}
      <SupportFloatingButton currentPath={path} />
    </>
  </StrictMode>,
)
