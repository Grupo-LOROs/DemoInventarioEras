import React from 'react'
import { authedFetch, getApiBase } from '../api'

export default function Discrepancies({ token }){
  const [rows, setRows] = React.useState([])

  React.useEffect(()=>{ load() }, [])

  async function load(){
    const r = await fetch(getApiBase() + '/discrepancies')
    if(r.ok){ setRows(await r.json()) } else { setRows([]) }
  }

  async function resolve(row){
    if(!token){ alert('Requiere sesión'); return }
    const note = window.prompt('Nota (opcional):','')
    await authedFetch('/discrepancies/resolve', { method:'POST', body: JSON.stringify({ product_id: row.product_id, discrepancy_type: row.discrepancy_type, note }) })
    load()
  }

  return (
    <div>
      <div className="row" style={{justifyContent:'space-between', marginBottom:10}}>
        <div style={{fontWeight:600}}>Discrepancias detectadas</div>
        <div>
          <button onClick={()=> window.open(getApiBase() + '/export/discrepancies.csv', '_blank')}>Exportar CSV</button>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Código</th>
            <th>Descripción</th>
            <th>Tipo</th>
            <th>Detalle</th>
            <th className="right">Stock</th>
            <th className="right">Costo</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.product_id + r.discrepancy_type}>
              <td className="mono">{r.id_code}</td>
              <td>{r.description}</td>
              <td>{r.discrepancy_type}</td>
              <td>{r.detail}</td>
              <td className="right">{r.stock}</td>
              <td className="right">{r.unit_cost ?? ''}</td>
              <td><button onClick={()=>resolve(r)}>Marcar resuelto</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
