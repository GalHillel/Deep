import axios from 'axios';

const client = axios.create({
    baseURL: '/api',
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add a helper to handle multi-repo context
export const setRepo = (repoName) => {
    client.defaults.params = repoName ? { repo: repoName } : {};
};

export default client;
