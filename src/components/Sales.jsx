import React from 'react'
import { getApiBase, authedFetch } from '../api'

export default function Sales({ token, role }){
  // role gates
  const canScanIN = role === 'admin' || role === 'purchasing'
  const canMakeSale = role === 'admin' || role === 'sales'

  // ---- SCAN-IN SECTION ----
  const [scanFile, setScanFile] = React.useState(null)
  const [scanBusy, setScanBusy] = React.useState(false)
  const [scanResult, setScanResult] = React.useState(null) // {count, barcodes:[{data,symbology,product}]}
  const [inQty, setInQty] = React.useState(1)
  const [inCost, setInCost] = React.useState('')

  async function decodeBarcode(){
    if(!scanFile) return alert('Selecciona una imagen')
    setScanBusy(true)
    try{
      const fd = new FormData()
      fd.append('file', scanFile)
      const r = await fetch(getApiBase() + '/barcode/decode', {
        method:'POST',
        headers: token ? {'Authorization':'Bearer '+token} : {},
        body: fd
      })
      const j = await r.json()
      if(!r.ok){ throw new Error(j.detail || 'Error decoding') }
      setScanResult(j)
    }catch(e){ alert(e.message) } finally { setScanBusy(false) }
  }

  async function addInventoryFromScan(b){
    if(!token) return alert('Requiere sesión')
    if(!canScanIN) return alert(`Tu rol (${role}) no puede ingresar inventario`)
    if(!b.product) return alert('Código desconocido: no hay producto con ese id_code')
    const body = {
      product_id: b.product.id,
      movement_type: 'IN',
      quantity: Number(inQty || 1),
      unit_cost: (inCost === '' ? null : Number(inCost)),
      movement_reason: 'SCAN_IN',
      note: `scan ${b.data}`
    }
    try{
      await authedFetch('/movements', { method:'POST', body: JSON.stringify(body) })
      alert('Inventario ingresado')
    }catch(e){ alert(e.message) }
  }

  // ---- SIMPLE SALE SECTION ----
  const [q, setQ] = React.useState('')
  const [typeId, setTypeId] = React.useState('')
  const [types, setTypes] = React.useState([])
  const [prodRows, setProdRows] = React.useState([])
  const [limit, setLimit] = React.useState(10)
  const [offset, setOffset] = React.useState(0)
  const [sort, setSort] = React.useState('id_code')
  const [order, setOrder] = React.useState('asc')
  const [selected, setSelected] = React.useState(null) // sticky selection

  React.useEffect(() => { (async () => {
    try{ const r = await fetch(getApiBase() + '/types'); if(r.ok) setTypes(await r.json()) }catch{}
  })() }, [])

  const [qDeb, setQDeb] = React.useState(q)
  React.useEffect(() => { const t = setTimeout(()=> setQDeb(q), 300); return () => clearTimeout(t) }, [q])

  React.useEffect(()=>{ loadProducts() }, [qDeb, typeId, limit, offset, sort, order])
  async function loadProducts(){
    const u = new URL(getApiBase() + '/products_full')
    if(qDeb) u.searchParams.set('q', qDeb)
    if(typeId) u.searchParams.set('type_id', typeId)
    u.searchParams.set('limit', limit); u.searchParams.set('offset', offset)
    u.searchParams.set('sort', sort); u.searchParams.set('order', order)
    const r = await fetch(u.toString()); if(r.ok){ const arr = await r.json(); setProdRows(arr) } else { setProdRows([]) }
  }

  React.useEffect(() => {
    if (!selected) return
    const m = prodRows.find(p => p.id === selected.id)
    if (m) setSelected(prev => ({ ...prev, ...m }))
  }, [prodRows]) // refresh sticky selection if visible

  function toggleSort(col){
    if (sort === col) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(col); setOrder('asc') }
    setOffset(0)
  }

  const [saleQty, setSaleQty] = React.useState(1)
  const [salePrice, setSalePrice] = React.useState('')   // optional override
  const [customer, setCustomer] = React.useState('')
  const [note, setNote] = React.useState('')

  async function makeSale(){
    if(!token) return alert('Requiere sesión')
    if(!canMakeSale) return alert(`Tu rol (${role}) no puede crear ventas`)
    if(!selected) return alert('Selecciona un producto')
    const body = {
      product_id: selected.id,
      quantity: Number(saleQty || 1),
      unit_price: salePrice === '' ? null : Number(salePrice),
      customer, note
    }
    try{
      const r = await authedFetch('/sales', { method:'POST', body: JSON.stringify(body) })
      const j = await r.json()
      alert(`Venta #${j.id} creada: ${j.id_code} x${j.quantity} total=${j.total}`)
    }catch(e){ alert(e.message) }
  }

  return (
    <div>
      <div className="row" style={{justifyContent:'space-between', alignItems:'center'}}>
        <div className="muted">Rol: <b>{role}</b> · Escaneo IN permitido: {canScanIN ? 'sí':'no'} · Ventas permitidas: {canMakeSale ? 'sí':'no'}</div>
        <div>
          <button onClick={()=> window.open(getApiBase() + '/export/sales.csv', '_blank')}>Exportar ventas CSV</button>
        </div>
      </div>

      {/* ---- Section A: Ingreso por escaneo ---- */}
      <div className="card mt-8">
        <div style={{fontWeight:600, marginBottom:10}}>A) Ingreso por escaneo (pyzbar)</div>
        <div className="row" style={{alignItems:'flex-end'}}>
          <div className="grow">
            <div className="muted">Imagen de código de barras</div>
            <input type="file" accept="image/*" onChange={e=> setScanFile(e.target.files?.[0] || null)} />
          </div>
          <div>
            <button className="btn-primary" onClick={decodeBarcode} disabled={scanBusy}>Decodificar</button>
          </div>
        </div>

        {scanResult && (
          <div className="mt-8">
            <div className="muted">Detectados: {scanResult.count}</div>
            <table className="mt-8" style={{width:'100%'}}>
              <thead><tr><th>Data</th><th>Simbología</th><th>Producto</th><th className="right">Cantidad</th><th className="right">Costo</th><th>Acción</th></tr></thead>
              <tbody>
                {scanResult.barcodes.map((b, i) => (
                  <tr key={i}>
                    <td className="mono">{b.data}</td>
                    <td>{b.symbology}</td>
                    <td>{b.product ? (<span><span className="mono">{b.product.id_code}</span> — {b.product.description}</span>) : <span className="muted">No encontrado</span>}</td>
                    <td className="right"><input type="number" value={inQty} onChange={e=>setInQty(e.target.value)} style={{width:90}} /></td>
                    <td className="right"><input type="number" value={inCost} onChange={e=>setInCost(e.target.value)} style={{width:110}} placeholder="(opcional)" /></td>
                    <td><button onClick={()=>addInventoryFromScan(b)} disabled={!canScanIN || !b.product}>Agregar IN</button></td>
                  </tr>
                ))}
                {scanResult.barcodes.length === 0 && <tr><td colSpan={6} className="muted">No se detectaron códigos</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ---- Section B: Venta simple ---- */}
      <div className="card mt-8">
        <div style={{fontWeight:600, marginBottom:10}}>B) Venta simple</div>
        <div className="row" style={{gap:12, alignItems:'flex-end'}}>
          <div className="grow">
            <div className="muted">Buscar producto</div>
            <input placeholder="Código o descripción" value={q} onChange={e=>{ setQ(e.target.value); setOffset(0); }} />
          </div>
          <div>
            <div className="muted">Tipo</div>
            <select value={typeId} onChange={e=>{ setTypeId(e.target.value); setOffset(0) }}>
              <option value="">Todos</option>
              {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <div className="muted">Filas</div>
            <select value={limit} onChange={e=>{ setLimit(Number(e.target.value)); setOffset(0) }}>
              <option value="10">10</option><option value="25">25</option><option value="50">50</option>
            </select>
          </div>
          <div>
            <div className="muted">Cantidad</div>
            <input type="number" value={saleQty} onChange={e=>setSaleQty(e.target.value)} />
          </div>
          <div>
            <div className="muted">Precio (opcional)</div>
            <input type="number" value={salePrice} onChange={e=>setSalePrice(e.target.value)} />
          </div>
        </div>

        {/* sticky selection pill */}
        {selected ? (
          <div className="row mt-8" style={{alignItems:'center', gap:8}}>
            <div className="muted">Seleccionado:</div>
            <div style={{border:'1px solid #e5e7eb', borderRadius:999, padding:'6px 10px', background:'#fff'}}>
              <span className="mono">{selected.id_code}</span> — {selected.description || ''}
            </div>
            <button onClick={()=> setSelected(null)}>Quitar</button>
            {!prodRows.some(p => p.id === selected.id) && (
              <div className="muted small">No visible en esta página/filtro, pero seguirá seleccionado.</div>
            )}
          </div>
        ) : <div className="muted small mt-8">Selecciona un producto para vender.</div>}

        <div className="mt-8" style={{border:'1px solid #e5e7eb', borderRadius:12, overflow:'hidden'}}>
          <table style={{width:'100%'}}>
            <thead>
              <tr>
                <th style={{width:40}}></th>
                <th className="sort" onClick={()=>toggleSort('id_code')}>Código {sort==='id_code' ? (order==='asc'?'▲':'▼'):''}</th>
                <th className="sort" onClick={()=>toggleSort('description')}>Descripción {sort==='description' ? (order==='asc'?'▲':'▼'):''}</th>
                <th className="right sort" onClick={()=>toggleSort('stock')}>Stock {sort==='stock' ? (order==='asc'?'▲':'▼'):''}</th>
                <th className="right sort" onClick={()=>toggleSort('unit_cost')}>Costo {sort==='unit_cost' ? (order==='asc'?'▲':'▼'):''}</th>
                <th className="sort" onClick={()=>toggleSort('product_type')}>Tipo {sort==='product_type' ? (order==='asc'?'▲':'▼'):''}</th>
              </tr>
            </thead>
            <tbody>
              {prodRows.map(p => (
                <tr key={p.id} style={{background: selected && selected.id===p.id ? '#f1f5f9':'transparent'}}>
                  <td>
                    <input type="checkbox" checked={!!selected && selected.id===p.id}
                      onChange={()=> setSelected(s => s && s.id===p.id ? null : p)} />
                  </td>
                  <td className="mono">{p.id_code}</td>
                  <td>{p.description}</td>
                  <td className="right">{p.stock}</td>
                  <td className="right">{p.unit_cost ?? ''}</td>
                  <td>{p.product_type ?? ''}</td>
                </tr>
              ))}
              {prodRows.length === 0 && <tr><td colSpan={6} className="muted">No hay resultados</td></tr>}
            </tbody>
          </table>
          <div className="row" style={{justifyContent:'space-between', padding:'10px 12px'}}>
            <div>
              <button onClick={()=> setOffset(Math.max(0, offset - limit))}>Anterior</button>
              <button onClick={()=> setOffset(offset + limit)} disabled={prodRows.length < limit}>Siguiente</button>
            </div>
            <div className="muted small">Mostrando {prodRows.length} (offset {offset}) · Orden: {sort} {order}</div>
          </div>
        </div>

        <div className="row mt-8">
          <div className="grow">
            <div className="muted">Cliente (opcional)</div>
            <input value={customer} onChange={e=>setCustomer(e.target.value)} />
          </div>
          <div className="grow">
            <div className="muted">Nota (opcional)</div>
            <input value={note} onChange={e=>setNote(e.target.value)} />
          </div>
          <div style={{alignSelf:'flex-end'}}>
            <button className="btn-primary" onClick={makeSale} disabled={!canMakeSale}>Crear venta</button>
          </div>
        </div>
      </div>
    </div>
  )
}
