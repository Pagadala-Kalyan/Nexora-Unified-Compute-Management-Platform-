// Local-first when the dashboard is served by the local control plane or Vite.
// Vercel users need the public control plane because their 127.0.0.1 is their
// own device, not the provider/control-plane machine.
const localHost=['localhost','127.0.0.1'].includes(window.location.hostname)||window.location.port==='8000';
const fallbackBase=import.meta.env.VITE_API_URL||(localHost?'http://127.0.0.1:8000':'https://nexora-unified-compute-management.onrender.com');
const sharedControlPlane=new URLSearchParams(window.location.search).get('controlPlane');
let base=sharedControlPlane||localStorage.getItem('nexora_control_plane')||fallbackBase;
if(sharedControlPlane)localStorage.setItem('nexora_control_plane',base);
let token=localStorage.getItem('nexora_token');
export function setToken(v){token=v; localStorage.setItem('nexora_token',v)}
export async function api(path,options={}){let r;try{r=await fetch(base+path,{...options,headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{ }),...(options.headers||{})}})}catch{throw new Error(`Control plane is unavailable at ${base}. Start the local backend or check the hosted service.`)}const data=await r.json();if(!r.ok)throw new Error(data.detail||'Request failed');return data}
