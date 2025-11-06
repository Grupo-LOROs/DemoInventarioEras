import React from 'react'
import { getApiBase, setApiBase, getToken, setToken, authedFetch, getRoleReliable} from './api'
import Products from './components/Products'
import Discrepancies from './components/Discrepancies'
import LowStock from './components/LowStock'
import Movements from './components/Movements'

export default function App(){
  const [token, setTok] = React.useState(getToken())
  const [apiBase, setBase] = React.useState(getApiBase())
  const [view, setView] = React.useState('products')
  const [banner, setBanner] = React.useState(null)
  const [role, setRole] = React.useState('user');

  React.useEffect(() => { (async () => setRole(await getRoleReliable()))(); }, []);

  const logout = () => { setTok(''); setToken('') }
  const login = async (email, password) => {
    const body = new URLSearchParams({username: email, password})
    const res = await fetch(getApiBase() + '/auth/login', {
      method: 'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body
    })
    if(!res.ok){ const t = await res.text(); throw new Error(t) }
    const data = await res.json()
    setTok(data.access_token); setToken(data.access_token);
    setRole(await getRoleReliable());   // <— refresh role after login
    setBanner({ok:true, text:'Sesión iniciada'}); setTimeout(()=>setBanner(null), 4000)
  }

  const testApi = async () => {
    try{
      const h = await authedFetch('/health'); const j = await h.json()
      setBanner({ok:true, text:'OK /health ' + (j.time || '')})
      const u = new URL(getApiBase() + '/products_full'); u.searchParams.set('limit', 1)
      const r = await fetch(u.toString()); if(!r.ok) throw new Error('products_full ' + r.status)
      const arr = await r.json(); setBanner({ok:true, text:'OK /products_full len=' + arr.length})
      setTimeout(()=>setBanner(null), 4000)
    }catch(e){ setBanner({ok:false, text: e.message }); }
  }

  const configApi = () => {
    const url = window.prompt('Base URL del API:', apiBase)
    if(url){ setBase(url); setApiBase(url) }
  }

  return (
    <div>
      <header>
        <div className="title">📦 Inventario Renovables</div>
        <div className="bar">
          <div className="tabs">
            <button aria-selected={view==='products'} onClick={()=>setView('products')}>Productos</button>
            <button aria-selected={view==='discrepancies'} onClick={()=>setView('discrepancies')}>Discrepancias</button>
            <button aria-selected={view==='lowstock'} onClick={()=>setView('lowstock')}>Bajo stock</button>
            <button aria-selected={view==='movements'} onClick={()=>setView('movements')}>Movimientos</button>
          </div>
          <button onClick={configApi}>Configurar API</button>
          <button onClick={testApi}>Probar API</button>
          <div className="muted" style={{alignSelf:'center'}}>Rol: <b>{role}</b></div>
          <button onClick={logout}>Salir</button>
        </div>
      </header>

      <div className="container">
        {banner && (
          <div className={'banner ' + (banner.ok ? 'banner-ok':'banner-warn')}>
            {banner.text}
          </div>
        )}
        <div className="card">
          <AuthBlock token={token} onLogin={login} apiBase={apiBase} />
          {view === 'products' && <Products token={token} />}
          {view === 'discrepancies' && <Discrepancies token={token} />}
          {view === 'lowstock' && <LowStock token={token} />}
          {view === 'movements' && <Movements token={token} role={role} />}
        </div>
      </div>
    </div>
  )
}

function AuthBlock({ token, onLogin, apiBase }){
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  return (
    <div>
      <div className="muted">API: {apiBase} {token ? ' | Autenticado' : ' | Invitado'}</div>
      {!token && (
        <div className="row mt-8">
          <input placeholder="Email" value={email} onChange={e=>setEmail(e.target.value)} />
          <input placeholder="Contraseña" type="password" value={password} onChange={e=>setPassword(e.target.value)} />
          <button className="btn-primary" onClick={()=>onLogin(email, password)}>Entrar</button>
        </div>
      )}
    </div>
  )
}
