import React from 'react'
import { authedFetch, getApiBase } from '../api'

export default function Products({ token }){
  const [q, setQ] = React.useState('')
  const [type, setType] = React.useState('')
  const [types, setTypes] = React.useState([])
  const [rows, setRows] = React.useState([])
  const [limit, setLimit] = React.useState(50)
  const [offset, setOffset] = React.useState(0)
  const [sort, setSort] = React.useState('id_code')
  const [order, setOrder] = React.useState('asc')
  const [editing, setEditing] = React.useState(null)
  const [historyFor, setHistoryFor] = React.useState(null)
  const [historyRows, setHistoryRows] = React.useState([])

  async function openHistory(row){
    setHistoryFor(row)
    const r = await fetch(`${getApiBase()}/products/${row.id}/movements?limit=50`)
    if(r.ok) setHistoryRows(await r.json()); else setHistoryRows([])
  }

  React.useEffect(()=>{ (async()=>{
    try{
      const r = await fetch(getApiBase() + '/types'); if(r.ok) setTypes(await r.json())
    }catch{}
  })() }, [])

  React.useEffect(()=>{ load() }, [q, type, limit, offset, sort, order])

  async function load(){
    const u = new URL(getApiBase() + '/products_full')
    if(q) u.searchParams.set('q', q)
    if(type) u.searchParams.set('type_id', type)
    u.searchParams.set('limit', limit)
    u.searchParams.set('offset', offset)
    u.searchParams.set('sort', sort)
    u.searchParams.set('order', order)
    const r = await fetch(u.toString())
    if(r.ok){ setRows(await r.json()) } else { setRows([]) }
  }

  async function saveEdit(){
    if(!editing) return
    const body = {
      description: editing.description,
      unit_cost: editing.unit_cost ? Number(editing.unit_cost) : null,
      min_stock: editing.min_stock ? Number(editing.min_stock) : null,
      max_stock: editing.max_stock ? Number(editing.max_stock) : null,
    }
    const res = await authedFetch('/products/' + editing.id, { method:'PATCH', body: JSON.stringify(body) })
    if(res.ok){ setEditing(null); setOffset(0); load() }
  }

  const toggleSort = (col) => {
    if(sort === col) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(col); setOrder('asc') }
  }

  return (
    <div>
      <div className="row" style={{marginBottom:10}}>
        <input placeholder="Buscar..." value={q} onChange={e=>setQ(e.target.value)} />
        <select value={type} onChange={e=>setType(e.target.value)}>
          <option value="">Todos los tipos</option>
          {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <select value={limit} onChange={e=>{ setLimit(Number(e.target.value)); setOffset(0) }}>
          <option value="25">25</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
        <button onClick={()=> window.open(getApiBase() + '/export/products.csv','_blank')}>Exportar CSV</button>
      </div>
      <div className="mt-8">
        <table>
          <thead>
            <tr>
              <th className="sort" onClick={()=>toggleSort('id_code')}>Código</th>
              <th className="sort" onClick={()=>toggleSort('description')}>Descripción</th>
              <th className="right sort" onClick={()=>toggleSort('stock')}>Stock</th>
              <th className="right sort" onClick={()=>toggleSort('unit_cost')}>Costo</th>
              <th className="right sort" onClick={()=>toggleSort('valuation')}>Valuación</th>
              <th className="sort" onClick={()=>toggleSort('product_type')}>Tipo</th>
              <th>Política</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id}>
                <td className="mono">{r.id_code}</td>
                <td>{r.description}</td>
                <td className="right">{r.stock}</td>
                <td className="right">{r.unit_cost ?? ''}</td>
                <td className="right">{r.valuation ?? ''}</td>
                <td>{r.product_type ?? ''}</td>
                <td className="muted">Min {r.min_stock ?? '-'} · Max {r.max_stock ?? '-'}</td>
                <td>
                  <button onClick={()=> setEditing(r)}>Editar</button>
                  <button onClick={()=> openHistory(r)} style={{marginLeft:8}}>Historial</button>
                </td>
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

      {editing && (
        <div className="modal-backdrop">
          <div className="modal">
            <div style={{fontWeight:600, marginBottom:10}}>Editar producto</div>
            <div className="row">
              <div>
                <div className="muted">Código</div>
                <div className="mono">{editing.id_code}</div>
              </div>
            </div>
            <div className="row mt-8">
              <div className="grow">
                <div className="muted">Descripción</div>
                <input value={editing.description||''} onChange={e=>setEditing({...editing, description:e.target.value})} />
              </div>
            </div>
            <div className="row mt-8">
              <div>
                <div className="muted">Costo Unit.</div>
                <input type="number" value={editing.unit_cost ?? ''} onChange={e=>setEditing({...editing, unit_cost:e.target.value})} />
              </div>
              <div>
                <div className="muted">Min Stock</div>
                <input type="number" value={editing.min_stock ?? ''} onChange={e=>setEditing({...editing, min_stock:e.target.value})} />
              </div>
              <div>
                <div className="muted">Max Stock</div>
                <input type="number" value={editing.max_stock ?? ''} onChange={e=>setEditing({...editing, max_stock:e.target.value})} />
              </div>
            </div>
            <div className="row mt-8" style={{justifyContent:'flex-end'}}>
              <button onClick={()=> setEditing(null)}>Cancelar</button>
              <button className="btn-primary" onClick={saveEdit}>Guardar</button>
            </div>
          </div>
        </div>
      )}
      
      {historyFor && (
      <div className="modal-backdrop">
        <div className="modal">
          <div style={{fontWeight:600, marginBottom:10}}>Historial — <span className="mono">{historyFor.id_code}</span></div>
          <table>
            <thead>
              <tr><th>Tipo</th><th className="right">Cantidad</th><th className="right">Costo</th><th>Fecha</th><th>Motivo</th><th>Nota</th></tr>
            </thead>
            <tbody>
              {historyRows.map(h => (
                <tr key={h.id}>
                  <td>{h.movement_type}</td>
                  <td className="right">{h.quantity}</td>
                  <td className="right">{h.unit_cost ?? ''}</td>
                  <td>{new Date(h.moved_at).toLocaleString()}</td>
                  <td>{h.movement_reason ?? ''}</td>
                  <td>{h.note ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row mt-8" style={{justifyContent:'flex-end'}}>
            <button onClick={()=> setHistoryFor(null)}>Cerrar</button>
          </div>
        </div>
      </div>
    )}

    </div>
  )
}
