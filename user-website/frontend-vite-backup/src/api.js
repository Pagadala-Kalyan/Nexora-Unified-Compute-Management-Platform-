// Local-first control plane. Set VITE_API_URL to a LAN address for teammates.
const base=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000';
let token=localStorage.getItem('nexora_token');
export function setToken(v){token=v; localStorage.setItem('nexora_token',v)}
export async function api(path,options={}){const r=await fetch(base+path,{...options,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{ }),...(options.headers||{})}});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Request failed');return data}
