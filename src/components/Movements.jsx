import React from 'react'
import { getApiBase, authedFetch } from '../api'

export default function Movements({ token, role }){
  // Role policy
  const allowedByRole = {
    admin: ['IN','OUT','ADJ'],
    sales: ['OUT'],
    purchasing: ['IN'],
    user: []
  };
  const allowedTypes = allowedByRole[role] || [];

  const [rows, setRows] = React.useState([]);
  const [limit, setLimit] = React.useState(50);
  const [offset, setOffset] = React.useState(0);

  // Product search + selection with pagination/sorting
  const [q, setQ] = React.useState('');
  const [typeId, setTypeId] = React.useState('');
  const [types, setTypes] = React.useState([]);
  const [productRows, setProductRows] = React.useState([]);
  const [prodLimit, setProdLimit] = React.useState(10);
  const [prodOffset, setProdOffset] = React.useState(0);
  const [prodSort, setProdSort] = React.useState('id_code'); // id_code | description | stock | unit_cost | valuation | product_type
  const [prodOrder, setProdOrder] = React.useState('asc');   // asc | desc
  const [selected, setSelected] = React.useState(null); // store the whole product

  // When new page of products arrives, refresh selected’s fields if it's visible now
  React.useEffect(() => {
    if (!selected) return;
    const match = productRows.find(p => p.id === selected.id);
    if (match) {
      // merge latest server fields (e.g., stock/unit_cost) but keep selection intact
      setSelected(prev => ({ ...prev, ...match }));
    }
  }, [productRows]); // eslint-disable-line

  // load persisted selection
  React.useEffect(() => {
    const saved = localStorage.getItem('mv_selected_id');
    const saved_code = localStorage.getItem('mv_selected_code');
    if (saved && saved_code) {
      // we don't know full fields yet—keep a minimal object, will hydrate when found in productRows
      setSelected({ id: Number(saved), id_code: saved_code, description: '(cargando...)' });
    }
  }, []);

  // persist/clear when selection changes
  React.useEffect(() => {
    if (selected) {
      localStorage.setItem('mv_selected_id', String(selected.id));
      localStorage.setItem('mv_selected_code', selected.id_code || '');
    } else {
      localStorage.removeItem('mv_selected_id');
      localStorage.removeItem('mv_selected_code');
    }
  }, [selected]);

  // Movement form
  const [form, setForm] = React.useState({
    movement_type: allowedTypes[0] || 'OUT',
    quantity: 1,
    unit_cost: '',
    movement_reason: '',
    note: ''
  });

  // Keep movement_type valid if role changes
  React.useEffect(() => {
    if (!allowedTypes.includes(form.movement_type)) {
      setForm(f => ({ ...f, movement_type: allowedTypes[0] || 'OUT' }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, allowedTypes.join(',')]);

  // Load movements list (bottom table)
  React.useEffect(()=>{ loadMovements() }, [limit, offset]);
  async function loadMovements(){
    const r = await fetch(`${getApiBase()}/movements?limit=${limit}&offset=${offset}`);
    if(r.ok) setRows(await r.json());
  }

  // Load product types (for filter)
  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(getApiBase() + '/types');
        if (r.ok) setTypes(await r.json());
      } catch {}
    })();
  }, []);

  // Debounced search trigger for product table
  const [qDebounced, setQDebounced] = React.useState(q);
  React.useEffect(() => {
    const t = setTimeout(() => setQDebounced(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  // Load the product table (picker)
  React.useEffect(() => {
    loadProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qDebounced, typeId, prodLimit, prodOffset, prodSort, prodOrder]);

  async function loadProducts(){
    const u = new URL(getApiBase() + '/products_full');
    if (qDebounced) u.searchParams.set('q', qDebounced);
    if (typeId) u.searchParams.set('type_id', typeId);
    u.searchParams.set('limit', prodLimit);
    u.searchParams.set('offset', prodOffset);
    u.searchParams.set('sort', prodSort);
    u.searchParams.set('order', prodOrder);
    const r = await fetch(u.toString());
    if (r.ok) {
      const arr = await r.json();
      setProductRows(arr);
    } else {
      setProductRows([]);
    }
  }

  function toggleProdSort(col){
    if (prodSort === col) {
      setProdOrder(prodOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setProdSort(col);
      setProdOrder('asc');
    }
    setProdOffset(0);
  }

  async function createMovement(){
    if(!token) return alert('Requiere sesión');
    if(!selected) return alert('Selecciona un producto');
    if(!allowedTypes.includes(form.movement_type)) {
      return alert(`Tu rol (${role}) no puede crear movimientos ${form.movement_type}`);
    }
    const body = {
      product_id: selected.id,
      movement_type: form.movement_type,
      quantity: Number(form.quantity),
      unit_cost: form.unit_cost === '' ? null : Number(form.unit_cost),
      movement_reason: form.movement_reason || null,
      note: form.note || null
    };
    try{
      await authedFetch('/movements', { method:'POST', body: JSON.stringify(body) });
      setOffset(0); loadMovements();
      alert('Movimiento creado');
    }catch(e){ alert(e.message); }
  }

  return (
    <div>
      {/* Product picker controls */}
      <div className="row" style={{gap:12, alignItems:'flex-end'}}>
        <div className="grow">
          <div className="muted">Buscar producto</div>
          <input placeholder="Código o descripción" value={q} onChange={e=>{ setQ(e.target.value); setProdOffset(0); }} />
        </div>
        <div>
          <div className="muted">Tipo</div>
          <select value={typeId} onChange={e => { setTypeId(e.target.value); setProdOffset(0); }}>
            <option value="">Todos</option>
            {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>
        <div>
          <div className="muted">Filas</div>
          <select value={prodLimit} onChange={e => { setProdLimit(Number(e.target.value)); setProdOffset(0); }}>
            <option value="10">10</option>
            <option value="25">25</option>
            <option value="50">50</option>
          </select>
        </div>
        <div>
          <div className="muted">Tipo movimiento</div>
          <select
            value={form.movement_type}
            onChange={e=>setForm(f=>({...f, movement_type:e.target.value}))}
            title={allowedTypes.length ? '' : 'Tu rol no permite crear movimientos'}
            disabled={allowedTypes.length === 0}
          >
            <option value="IN"  disabled={!allowedTypes.includes('IN')}>IN</option>
            <option value="OUT" disabled={!allowedTypes.includes('OUT')}>OUT</option>
            <option value="ADJ" disabled={!allowedTypes.includes('ADJ')}>ADJ</option>
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
      </div>

      <div className="muted small" style={{marginTop:6}}>
        Rol: <b>{role}</b> · Permitidos: {allowedTypes.join(', ') || 'ninguno'}
      </div>

      {selected ? (
        <div className="row mt-8" style={{alignItems:'center', gap:8}}>
          <div className="muted">Producto seleccionado:</div>
          <div style={{border:'1px solid #e5e7eb', borderRadius:999, padding:'6px 10px', background:'#fff'}}>
            <span className="mono">{selected.id_code}</span> — {selected.description || ''}
          </div>
          <button onClick={()=> setSelected(null)}>Quitar</button>
          {/* If not currently visible under filters, show a hint */}
          {!productRows.some(p => p.id === selected.id) && (
            <div className="muted small">No aparece en esta página/filtro, pero seguirá seleccionado.</div>
          )}
        </div>
      ) : (
        <div className="muted small mt-8">Selecciona un producto de la tabla para crear el movimiento.</div>
      )}

      {/* Product picker table (sortable, paginated, single-select) */}
      <div className="mt-8" style={{border:'1px solid #e5e7eb', borderRadius:12, overflow:'hidden'}}>
        <table style={{width:'100%'}}>
          <thead>
            <tr>
              <th style={{width:40}}></th>
              <th className="sort" onClick={()=>toggleProdSort('id_code')}>Código {prodSort==='id_code' ? (prodOrder==='asc'?'▲':'▼') : ''}</th>
              <th className="sort" onClick={()=>toggleProdSort('description')}>Descripción {prodSort==='description' ? (prodOrder==='asc'?'▲':'▼') : ''}</th>
              <th className="right sort" onClick={()=>toggleProdSort('stock')}>Stock {prodSort==='stock' ? (prodOrder==='asc'?'▲':'▼') : ''}</th>
              <th className="right sort" onClick={()=>toggleProdSort('unit_cost')}>Costo {prodSort==='unit_cost' ? (prodOrder==='asc'?'▲':'▼') : ''}</th>
              <th className="sort" onClick={()=>toggleProdSort('product_type')}>Tipo {prodSort==='product_type' ? (prodOrder==='asc'?'▲':'▼') : ''}</th>
            </tr>
          </thead>
          <tbody>
            {productRows.map(p => (
              <tr key={p.id} style={{background: selected===p.id ? '#f1f5f9':'transparent'}}>
                <td>
                  <input
                    type="checkbox"
                    checked={!!selected && selected.id === p.id}
                    onChange={() => setSelected(s => (s && s.id === p.id ? null : p))}
                  />
                </td>
                <td className="mono">{p.id_code}</td>
                <td>{p.description}</td>
                <td className="right">{p.stock}</td>
                <td className="right">{p.unit_cost ?? ''}</td>
                <td>{p.product_type ?? ''}</td>
              </tr>
            ))}
            {productRows.length === 0 && (
              <tr><td colSpan={6} className="muted">No hay resultados</td></tr>
            )}
          </tbody>
        </table>
        <div className="row" style={{justifyContent:'space-between', padding:'10px 12px'}}>
          <div>
            <button onClick={()=> setProdOffset(Math.max(0, prodOffset - prodLimit))}>Anterior</button>
            <button
              onClick={()=> setProdOffset(prodOffset + prodLimit)}
              disabled={productRows.length < prodLimit}  // naive next-page guard
            >
              Siguiente
            </button>
          </div>
          <div className="muted small">Mostrando {productRows.length} (offset {prodOffset}) · Orden: {prodSort} {prodOrder}</div>
        </div>
      </div>

      {/* Optional fields below the table */}
      <div className="row mt-8">
        <div className="grow">
          <div className="muted">Motivo (opcional)</div>
          <input value={form.movement_reason} onChange={e=>setForm(f=>({...f, movement_reason:e.target.value}))} />
        </div>
        <div className="grow">
          <div className="muted">Nota (opcional)</div>
          <input value={form.note} onChange={e=>setForm(f=>({...f, note:e.target.value}))} />
        </div>
        <div style={{alignSelf:'flex-end'}}>
          <button
            className="btn-primary"
            onClick={()=>{
              if (!allowedTypes.includes(form.movement_type)) {
                return alert(`Tu rol (${role}) no puede crear movimientos ${form.movement_type}`);
              }
              createMovement();
            }}
            disabled={allowedTypes.length === 0}
          >
            Crear movimiento
          </button>
        </div>
      </div>

      {/* Movements list */}
      <div className="row mt-16" style={{justifyContent:'space-between', alignItems:'center'}}>
        <div className="muted">Movimientos recientes</div>
        <div>
          <button onClick={()=> window.open(getApiBase() + '/export/movements.csv', '_blank')}>Exportar CSV</button>
        </div>
      </div>
      <table className="mt-8">
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
