import React from 'react'
import { getApiBase } from '../api'

export default function LowStock({ token }){
  const [rows, setRows] = React.useState([])
  const [bulkOpen, setBulkOpen] = React.useState(false)
  const [bulkText, setBulkText] = React.useState('')

  React.useEffect(()=>{ load() }, [])

  async function load(){
    const r = await fetch(getApiBase() + '/reports/low_stock')
    if(r.ok){ setRows(await r.json()) } else { setRows([]) }
  }

  async function sendBulk(){
    if(!token){ alert('Requiere sesión (admin)'); return }
    let payload = []
    try{ payload = JSON.parse(bulkText || '[]') }catch(e){ return alert('JSON inválido') }
    const res = await fetch(getApiBase() + '/policies/bulk_minmax', {
      method:'POST',
      headers: { 'Content-Type':'application/json', 'Authorization':'Bearer '+token },
      body: JSON.stringify(payload)
    })
    if(!res.ok){ const t = await res.text(); return alert('Error: ' + t) }
    setBulkOpen(false); setBulkText(''); load()
  }

  return (
    <div>
      <div className="row" style={{justifyContent:'space-between', marginBottom:10}}>
        <div style={{fontWeight:600}}>Bajo stock</div>
        <div>
          <button onClick={()=> window.open(getApiBase() + '/export/low_stock.csv', '_blank')}>Exportar CSV</button>
          <button onClick={()=> setBulkOpen(true)} style={{marginLeft:8}}>Cargar min/max</button>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Código</th>
            <th>Descripción</th>
            <th>Tipo</th>
            <th className="right">Stock</th>
            <th className="right">Min</th>
            <th className="right">Faltante</th>
            <th className="right">Costo Unit.</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.codigo}>
              <td className="mono">{r.codigo}</td>
              <td>{r.descripcion}</td>
              <td>{r.tipo ?? ''}</td>
              <td className="right">{r.stock}</td>
              <td className="right">{r.min_stock ?? ''}</td>
              <td className="right">{r.faltante}</td>
              <td className="right">{r.costo_unitario ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {bulkOpen && (
        <div className="modal-backdrop">
          <div className="modal">
            <div style={{fontWeight:600, marginBottom:10}}>Cargar min/max (JSON)</div>
            <div className="muted small">Formato: [{{"id_code":"ABC123","min_stock":10,"max_stock":50}}, ...]</div>
            <textarea style={{width:'100%', height:160}} value={bulkText} onChange={e=>setBulkText(e.target.value)} />
            <div className="row mt-8" style={{justifyContent:'flex-end'}}>
              <button onClick={()=> setBulkOpen(false)}>Cancelar</button>
              <button className="btn-primary" onClick={sendBulk}>Enviar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
