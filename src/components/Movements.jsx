import React from 'react'
import { getApiBase, authedFetch } from '../api'

export default function Movements({ token }){
  const [rows, setRows] = React.useState([])
  const [limit, setLimit] = React.useState(50)
  const [offset, setOffset] = React.useState(0)
  const [form, setForm] = React.useState({ productQuery:'', product:null, movement_type:'OUT', quantity:1, unit_cost:'', movement_reason:'', note:'' })
  const [picker, setPicker] = React.useState([])

  React.useEffect(()=>{ load() }, [limit, offset])

  async function load(){
    const r = await fetch(`${getApiBase()}/movements?limit=${limit}&offset=${offset}`)
    if(r.ok) setRows(await r.json())
  }

  async function searchProducts(q){
    setForm(f => ({...f, productQuery:q}))
    if(!q) return setPicker([])
    const url = new URL(getApiBase() + '/products_full')
    url.searchParams.set('q', q); url.searchParams.set('limit', 10)
    const r = await fetch(url.toString()); if(!r.ok) return setPicker([])
    const arr = await r.json(); setPicker(arr)
  }

  async function createMovement(){
    if(!token) return alert('Requiere sesión')
    if(!form.product) return alert('Selecciona producto')
    const body = {
      product_id: form.product.id,
      movement_type: form.movement_type,
      quantity: Number(form.quantity),
      unit_cost: form.unit_cost === '' ? null : Number(form.unit_cost),
      movement_reason: form.movement_reason || null,
      note: form.note || null
    }
    try{
      await authedFetch('/movements', { method:'POST', body: JSON.stringify(body) })
      setForm({ productQuery:'', product:null, movement_type:'OUT', quantity:1, unit_cost:'', movement_reason:'', note:'' })
      setPicker([]); setOffset(0); load()
      alert('Movimiento creado')
    }catch(e){ alert(e.message) }
  }

  return (
    <div>
      <div className="row" style={{marginBottom:10, alignItems:'flex-start'}}>
        <div style={{flex:1}}>
          <div className="muted">Producto</div>
          <input placeholder="Buscar por código o descripción" value={form.productQuery} onChange={e=>searchProducts(e.target.value)} />
          {picker.length>0 && (
            <div style={{border:'1px solid #e5e7eb', borderRadius:8, marginTop:6, maxHeight:180, overflowY:'auto', background:'#fff'}}>
              {picker.map(p => (
                <div key={p.id} style={{padding:8, cursor:'pointer'}} onClick={()=>{ setForm(f=>({...f, product:p, productQuery:`${p.id_code} — ${p.description||''}`})); setPicker([]) }}>
                  <span className="mono">{p.id_code}</span> — {p.description}
                </div>
              ))}
            </div>
          )}
          {form.product && <div className="muted mt-8">Seleccionado: <span className="mono">{form.product.id_code}</span></div>}
        </div>
        <div>
          <div className="muted">Tipo</div>
          <select value={form.movement_type} onChange={e=>setForm(f=>({...f, movement_type:e.target.value}))}>
            <option value="IN">IN</option>
            <option value="OUT">OUT</option>
            <option value="ADJ">ADJ</option>
          </select>
        </div>
        <div>
          <div className="muted">Cantidad</div>
          <input type="number" value={form.quantity} onChange={e=>setForm(f=>({...f, quantity:e.target.value}))} />
        </div>
        <div>
          <div className="muted">Costo Unit. (opcional)</div>
          <input type="number" value={form.unit_cost} onChange={e=>setForm(f=>({...f, unit_cost:e.target.value}))} />
        </div>
        <div className="grow">
          <div className="muted">Motivo (opcional)</div>
          <input value={form.movement_reason} onChange={e=>setForm(f=>({...f, movement_reason:e.target.value}))} />
        </div>
        <div className="grow">
          <div className="muted">Nota (opcional)</div>
          <input value={form.note} onChange={e=>setForm(f=>({...f, note:e.target.value}))} />
        </div>
        <div style={{alignSelf:'flex-end'}}>
          <button className="btn-primary" onClick={createMovement}>Crear movimiento</button>
        </div>
      </div>

      <div className="row" style={{justifyContent:'space-between', marginBottom:10}}>
        <div className="muted">Movimientos recientes</div>
        <div>
          <button onClick={()=> window.open(getApiBase() + '/export/movements.csv', '_blank')}>Exportar CSV</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Código</th><th>Descripción</th><th>Tipo</th>
            <th className="right">Cantidad</th><th className="right">Costo</th><th>Fecha</th><th>Motivo</th><th>Nota</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id}>
              <td className="mono">{r.id_code}</td>
              <td>{r.description}</td>
              <td>{r.movement_type}</td>
              <td className="right">{r.quantity}</td>
              <td className="right">{r.unit_cost ?? ''}</td>
              <td>{new Date(r.moved_at).toLocaleString()}</td>
              <td>{r.movement_reason ?? ''}</td>
              <td>{r.note ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="row mt-8" style={{justifyContent:'space-between'}}>
        <div>
          <button onClick={()=> setOffset(Math.max(0, offset - limit))}>Anterior</button>
          <button onClick={()=> setOffset(offset + limit)}>Siguiente</button>
        </div>
        <div className="muted">Mostrando {rows.length} (offset {offset})</div>
      </div>
    </div>
  )
}
