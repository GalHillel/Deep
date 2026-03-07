import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            refetchOnWindowFocus: false,
            retry: 1,
        },
    },
})

const root = document.getElementById('root');
if (root) {
    try {
        ReactDOM.createRoot(root).render(
            <React.StrictMode>
                <QueryClientProvider client={queryClient}>
                    <App />
                </QueryClientProvider>
            </React.StrictMode>,
        )
        console.log("DeepGit UI Mounted Successfully");
    } catch (err) {
        console.error("DeepGit UI Render Error:", err);
        root.innerHTML = `<div style="padding: 20px; color: red;"><h2>UI Render Error</h2><pre>${err.message}</pre></div>`;
    }
} else {
    console.error("Root element not found");
}
