// Local runs use FastAPI on port 8000. Hosted deployments should set
// VITE_API_URL to the separately deployed Nexora control-plane URL.
const base=import.meta.env.VITE_API_URL||'https://nexora-unified-compute-management.onrender.com';
let token=localStorage.getItem('nexora_token');
export function setToken(v){token=v; localStorage.setItem('nexora_token',v)}
export async function api(path,options={}){const r=await fetch(base+path,{...options,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{ }),...(options.headers||{})}});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Request failed');return data}
