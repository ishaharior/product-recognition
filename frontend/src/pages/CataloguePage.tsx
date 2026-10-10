import { useEffect, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { Pencil, Plus, Trash2, X } from 'lucide-react';
import { ApiError, api } from '../services/api';
import EmptyState from '../components/EmptyState';
import Modal from '../components/Modal';
import type { Product, ProductPayload } from '../types';
import { formatWeight, hexForColour } from '../utils/format';
import '../styles/pages.css';

interface VariantRow {
  colour_name: string;
  hex_value: string;
  primary_variant: boolean;
}

interface FormModel {
  sku: string;
  name: string;
  category: string;
  description: string;
  weight_spec_kind: 'gross' | 'net';
  expected_gross_weight_g: string;
  expected_net_weight_g: string;
  packaging_weight_g: string;
  weight_tolerance_pct: string;
  model_class_names: string;
  active: boolean;
  colour_variants: VariantRow[];
}

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

const EMPTY_FORM: FormModel = {
  sku: '',
  name: '',
  category: '',
  description: '',
  weight_spec_kind: 'gross',
  expected_gross_weight_g: '',
  expected_net_weight_g: '',
  packaging_weight_g: '',
  weight_tolerance_pct: '10',
  model_class_names: '',
  active: true,
  colour_variants: [],
};

function formFromProduct(p: Product | null): FormModel {
  if (!p) return { ...EMPTY_FORM, colour_variants: [] };
  return {
    sku: p.sku,
    name: p.name,
    category: p.category ?? '',
    description: p.description ?? '',
    weight_spec_kind: p.weight_spec_kind ?? 'gross',
    expected_gross_weight_g: p.expected_gross_weight_g === null ? '' : String(p.expected_gross_weight_g),
    expected_net_weight_g: p.expected_net_weight_g === null ? '' : String(p.expected_net_weight_g),
    packaging_weight_g: p.packaging_weight_g === null ? '' : String(p.packaging_weight_g),
    weight_tolerance_pct: String(p.weight_tolerance_pct ?? 10),
    model_class_names: p.model_class_names ?? '',
    active: p.active,
    colour_variants: (p.colour_variants ?? []).map((v) => ({
      colour_name: v.colour_name,
      hex_value: v.hex_value,
      primary_variant: v.primary_variant,
    })),
  };
}

function toNumberOrNull(v: string): number | null {
  const t = v.trim();
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

function validate(form: FormModel): Record<string, string> {
  const errs: Record<string, string> = {};
  if (!form.sku.trim()) errs.sku = 'SKU is required.';
  else if (/\s/.test(form.sku)) errs.sku = 'SKU must not contain spaces.';
  if (!form.name.trim()) errs.name = 'Name is required.';

  const tol = form.weight_tolerance_pct.trim();
  if (!tol || !Number.isFinite(Number(tol)) || Number(tol) < 0 || Number(tol) > 100) {
    errs.weight_tolerance_pct = 'Tolerance must be a number between 0 and 100.';
  }

  const numericKeys = ['expected_gross_weight_g', 'expected_net_weight_g', 'packaging_weight_g'] as const;
  for (const key of numericKeys) {
    const raw = form[key].trim();
    if (raw && !Number.isFinite(Number(raw))) errs[key] = 'Enter a number (grams).';
  }

  form.colour_variants.forEach((v, i) => {
    if (!v.colour_name.trim()) errs[`variant-${i}`] = 'Colour name is required.';
    const hex = v.hex_value.trim();
    if (hex && !HEX_RE.test(hex)) errs[`hex-${i}`] = 'Use a hex colour like #e63946.';
  });

  return errs;
}

function variantHex(v: { colour_name: string; hex_value: string }): string {
  const hex = (v.hex_value ?? '').trim();
  return HEX_RE.test(hex) ? hex : hexForColour(v.colour_name);
}

function fieldError(errors: Record<string, string>, key: string): ReactNode {
  return errors[key] ? <span className="field-error">{errors[key]}</span> : null;
}

export default function CataloguePage() {
  const [items, setItems] = useState<Product[]>([]);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [editing, setEditing] = useState<'new' | Product | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Product | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [form, setForm] = useState<FormModel>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const reload = (): void => setReloadKey((k) => k + 1);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const t = window.setTimeout(() => {
      api
        .listProducts({ search, limit: 200 })
        .then((res) => {
          if (!alive) return;
          setItems(res.items);
          setError(null);
        })
        .catch((e: unknown) => {
          if (!alive) return;
          setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, 250);
    return () => {
      alive = false;
      window.clearTimeout(t);
    };
  }, [search, reloadKey]);

  useEffect(() => {
    if (!flash) return;
    const t = window.setTimeout(() => setFlash(null), 4000);
    return () => window.clearTimeout(t);
  }, [flash]);

  const categories = Array.from(new Set(items.map((p) => p.category).filter(Boolean))).sort();
  const filtered = category ? items.filter((p) => p.category === category) : items;

  const openNew = (): void => {
    setForm(formFromProduct(null));
    setFormErrors({});
    setEditing('new');
  };

  const openEdit = (p: Product): void => {
    setForm(formFromProduct(p));
    setFormErrors({});
    setEditing(p);
  };

  const updateField = <K extends keyof FormModel>(key: K, value: FormModel[K]): void => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const updateVariant = (index: number, patch: Partial<VariantRow>): void => {
    setForm((prev) => ({
      ...prev,
      colour_variants: prev.colour_variants.map((v, i) => (i === index ? { ...v, ...patch } : v)),
    }));
  };

  const setPrimaryVariant = (index: number): void => {
    setForm((prev) => ({
      ...prev,
      colour_variants: prev.colour_variants.map((v, i) => ({ ...v, primary_variant: i === index })),
    }));
  };

  const addVariant = (): void => {
    setForm((prev) => ({
      ...prev,
      colour_variants: [
        ...prev.colour_variants,
        { colour_name: '', hex_value: '', primary_variant: prev.colour_variants.length === 0 },
      ],
    }));
  };

  const removeVariant = (index: number): void => {
    setForm((prev) => {
      const next = prev.colour_variants.filter((_, i) => i !== index);
      if (next.length > 0 && !next.some((v) => v.primary_variant)) next[0].primary_variant = true;
      return { ...prev, colour_variants: next };
    });
  };

  const submit = async (e: FormEvent): Promise<void> => {
    e.preventDefault();
    const errs = validate(form);
    setFormErrors(errs);
    if (Object.keys(errs).length > 0) return;

    const payload: ProductPayload = {
      sku: form.sku.trim(),
      name: form.name.trim(),
      category: form.category.trim(),
      description: form.description.trim(),
      weight_spec_kind: form.weight_spec_kind,
      expected_gross_weight_g: toNumberOrNull(form.expected_gross_weight_g),
      expected_net_weight_g: toNumberOrNull(form.expected_net_weight_g),
      packaging_weight_g: toNumberOrNull(form.packaging_weight_g),
      weight_tolerance_pct: Number(form.weight_tolerance_pct),
      model_class_names: form.model_class_names.trim(),
      active: form.active,
      colour_variants: form.colour_variants.map((v) => ({
        colour_name: v.colour_name.trim(),
        hex_value: v.hex_value.trim(),
        primary_variant: v.primary_variant,
      })),
    };

    setSaving(true);
    try {
      if (editing === 'new') await api.createProduct(payload);
      else if (editing) await api.updateProduct(editing.id, payload);
      setEditing(null);
      setFlash('Product saved');
      reload();
    } catch (e: unknown) {
      const detail = e instanceof ApiError ? e.detail : e instanceof Error ? e.message : 'Save failed.';
      setFormErrors({ _form: detail });
    } finally {
      setSaving(false);
    }
  };

  const confirmDelete = async (): Promise<void> => {
    if (!deleteTarget) return;
    try {
      await api.deleteProduct(deleteTarget.id);
      setDeleteTarget(null);
      setDeleteError(null);
      setFlash('Product deleted');
      reload();
    } catch (e: unknown) {
      setDeleteError(e instanceof ApiError ? e.detail : e instanceof Error ? e.message : 'Delete failed.');
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Product catalogue</h1>
          <p className="page-sub">
            Expected weights, tolerances, colour variants and detector classes used by the verifier.
          </p>
        </div>
        <div className="page-actions">
          <label className="sr-only" htmlFor="product-search">
            Search products
          </label>
          <input
            id="product-search"
            className="input"
            style={{ width: 240 }}
            placeholder="Search name, SKU, category…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <label className="sr-only" htmlFor="product-category">
            Filter by category
          </label>
          <select
            id="product-category"
            className="select"
            style={{ width: 170 }}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button type="button" className="btn btn-primary" onClick={openNew}>
            <Plus size={15} aria-hidden="true" /> New product
          </button>
        </div>
      </div>

      {flash ? <div className="notice info mb-16">{flash}</div> : null}
      {error ? <div className="notice danger mb-16">{error}</div> : null}

      <div className="panel">
        <h2 className="panel-title">
          Products
          <span className="hint">{loading ? 'loading…' : `${filtered.length} shown`}</span>
        </h2>
        {loading && items.length === 0 ? (
          <div className="empty-state">
            <span className="spinner" aria-hidden="true" />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title={items.length === 0 ? 'No products yet' : 'No products match the current filters'}
            message={
              items.length === 0
                ? 'Create your first product or run the backend seeding (data/product_specs.csv).'
                : 'Clear the search or category filter to see everything again.'
            }
            action={
              <button type="button" className="btn btn-primary mt-16" onClick={openNew}>
                <Plus size={15} aria-hidden="true" /> New product
              </button>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Product</th>
                  <th>Category</th>
                  <th>Colours</th>
                  <th>Weight</th>
                  <th>Tolerance</th>
                  <th>Model classes</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => {
                  const primary = (p.colour_variants ?? []).find((v) => v.primary_variant) ?? p.colour_variants?.[0];
                  const others = (p.colour_variants ?? []).filter((v) => v !== primary);
                  return (
                    <tr key={p.id}>
                      <td className="mono nowrap">{p.sku}</td>
                      <td>
                        <div>{p.name}</div>
                        {p.description ? <div className="faint truncate">{p.description}</div> : null}
                      </td>
                      <td>
                        {p.category ? <span className="tag">{p.category}</span> : <span className="faint">—</span>}
                      </td>
                      <td className="nowrap">
                        {primary ? (
                          <>
                            <span className="swatch" style={{ background: variantHex(primary) }} />
                            {primary.colour_name}
                          </>
                        ) : (
                          <span className="faint">—</span>
                        )}
                        {others.map((v, i) => (
                          <span
                            key={`${v.colour_name}-${i}`}
                            className="swatch"
                            style={{ background: variantHex(v), marginLeft: 4 }}
                            title={v.colour_name}
                          />
                        ))}
                      </td>
                      <td className="nowrap">
                        {formatWeight(p.expected_gross_weight_g)}
                        {p.expected_net_weight_g !== null ? (
                          <span className="faint"> · net {formatWeight(p.expected_net_weight_g)}</span>
                        ) : null}{' '}
                        <span className="tag">{p.weight_spec_kind}</span>
                      </td>
                      <td className="nowrap">±{p.weight_tolerance_pct}%</td>
                      <td>
                        {p.model_class_names ? (
                          <span className="faint mono truncate">{p.model_class_names}</span>
                        ) : (
                          <span className="faint">—</span>
                        )}
                      </td>
                      <td>
                        {p.active ? (
                          <span className="badge badge-ok">Active</span>
                        ) : (
                          <span className="badge badge-neutral">Inactive</span>
                        )}
                      </td>
                      <td>
                        <div className="row">
                          <button
                            type="button"
                            className="btn btn-sm"
                            aria-label={`Edit ${p.name}`}
                            onClick={() => openEdit(p)}
                          >
                            <Pencil size={14} aria-hidden="true" /> Edit
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            aria-label={`Delete ${p.name}`}
                            onClick={() => {
                              setDeleteError(null);
                              setDeleteTarget(p);
                            }}
                          >
                            <Trash2 size={14} aria-hidden="true" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing ? (
        <Modal
          title={editing === 'new' ? 'New product' : `Edit ${editing.name}`}
          onClose={() => setEditing(null)}
          actions={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setEditing(null)}>
                Cancel
              </button>
              <button
                type="submit"
                form="product-form"
                className="btn btn-primary"
                disabled={saving}
              >
                {saving ? 'Saving…' : 'Save product'}
              </button>
            </>
          }
        >
          <form id="product-form" onSubmit={(e) => void submit(e)} noValidate>
            {formErrors._form ? <div className="notice danger mb-8">{formErrors._form}</div> : null}

            <div className="form-row">
              <div className="field">
                <label htmlFor="f-sku">SKU *</label>
                <input
                  id="f-sku"
                  className={`input${formErrors.sku ? ' error' : ''}`}
                  value={form.sku}
                  onChange={(e) => updateField('sku', e.target.value)}
                  placeholder="SKU-COLA-355"
                />
                {fieldError(formErrors, 'sku')}
              </div>
              <div className="field">
                <label htmlFor="f-name">Name *</label>
                <input
                  id="f-name"
                  className={`input${formErrors.name ? ' error' : ''}`}
                  value={form.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  placeholder="Cola can 355 ml"
                />
                {fieldError(formErrors, 'name')}
              </div>
            </div>

            <div className="form-row">
              <div className="field">
                <label htmlFor="f-category">Category</label>
                <input
                  id="f-category"
                  className="input"
                  value={form.category}
                  onChange={(e) => updateField('category', e.target.value)}
                  placeholder="beverages"
                />
              </div>
              <div className="field">
                <label htmlFor="f-kind">Weight spec</label>
                <select
                  id="f-kind"
                  className="select"
                  value={form.weight_spec_kind}
                  onChange={(e) => updateField('weight_spec_kind', e.target.value as 'gross' | 'net')}
                >
                  <option value="gross">gross (product + packaging)</option>
                  <option value="net">net (product only)</option>
                </select>
              </div>
            </div>

            <div className="field">
              <label htmlFor="f-description">Description</label>
              <textarea
                id="f-description"
                className="textarea"
                rows={2}
                value={form.description}
                onChange={(e) => updateField('description', e.target.value)}
              />
            </div>

            <div className="form-row">
              <div className="field">
                <label htmlFor="f-gross">Expected gross weight (g)</label>
                <input
                  id="f-gross"
                  className={`input${formErrors.expected_gross_weight_g ? ' error' : ''}`}
                  inputMode="decimal"
                  value={form.expected_gross_weight_g}
                  onChange={(e) => updateField('expected_gross_weight_g', e.target.value)}
                  placeholder="355"
                />
                {fieldError(formErrors, 'expected_gross_weight_g')}
              </div>
              <div className="field">
                <label htmlFor="f-net">Expected net weight (g)</label>
                <input
                  id="f-net"
                  className={`input${formErrors.expected_net_weight_g ? ' error' : ''}`}
                  inputMode="decimal"
                  value={form.expected_net_weight_g}
                  onChange={(e) => updateField('expected_net_weight_g', e.target.value)}
                  placeholder="330"
                />
                {fieldError(formErrors, 'expected_net_weight_g')}
              </div>
            </div>

            <div className="form-row">
              <div className="field">
                <label htmlFor="f-packaging">Packaging weight (g)</label>
                <input
                  id="f-packaging"
                  className={`input${formErrors.packaging_weight_g ? ' error' : ''}`}
                  inputMode="decimal"
                  value={form.packaging_weight_g}
                  onChange={(e) => updateField('packaging_weight_g', e.target.value)}
                  placeholder="25"
                />
                {fieldError(formErrors, 'packaging_weight_g')}
              </div>
              <div className="field">
                <label htmlFor="f-tolerance">Weight tolerance (%)</label>
                <input
                  id="f-tolerance"
                  className={`input${formErrors.weight_tolerance_pct ? ' error' : ''}`}
                  inputMode="decimal"
                  value={form.weight_tolerance_pct}
                  onChange={(e) => updateField('weight_tolerance_pct', e.target.value)}
                />
                {fieldError(formErrors, 'weight_tolerance_pct')}
              </div>
            </div>

            <div className="field">
              <label htmlFor="f-classes">Model class names</label>
              <input
                id="f-classes"
                className="input"
                value={form.model_class_names}
                onChange={(e) => updateField('model_class_names', e.target.value)}
                placeholder="bottle, can, box"
              />
              <span className="help">
                Comma-separated detector class names this product maps to (custom model classes or COCO labels).
              </span>
            </div>

            <div className="field">
              <label htmlFor="f-active" className="row">
                <input
                  id="f-active"
                  type="checkbox"
                  checked={form.active}
                  onChange={(e) => updateField('active', e.target.checked)}
                />
                Active (participates in verification)
              </label>
            </div>

            <div className="field">
              <label>Colour variants</label>
              {form.colour_variants.length === 0 ? (
                <div className="faint mb-8">No colour variants yet.</div>
              ) : null}
              {form.colour_variants.map((v, i) => (
                <div key={`variant-${i}`} className="mb-8">
                  <div className="row">
                    <input
                      className={`input${formErrors[`variant-${i}`] ? ' error' : ''}`}
                      value={v.colour_name}
                      aria-label={`Colour ${i + 1} name`}
                      placeholder="Colour name"
                      onChange={(e) => updateVariant(i, { colour_name: e.target.value })}
                    />
                    <input
                      className={`input${formErrors[`hex-${i}`] ? ' error' : ''}`}
                      style={{ maxWidth: 130 }}
                      value={v.hex_value}
                      aria-label={`Colour ${i + 1} hex value`}
                      placeholder="#e63946"
                      onChange={(e) => updateVariant(i, { hex_value: e.target.value })}
                    />
                    <label className="row faint nowrap" htmlFor={`f-primary-${i}`}>
                      <input
                        id={`f-primary-${i}`}
                        type="radio"
                        name="primary-colour"
                        checked={v.primary_variant}
                        onChange={() => setPrimaryVariant(i)}
                      />
                      primary
                    </label>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      aria-label={`Remove colour ${i + 1}`}
                      onClick={() => removeVariant(i)}
                    >
                      <X size={14} aria-hidden="true" />
                    </button>
                  </div>
                  {fieldError(formErrors, `variant-${i}`)}
                  {fieldError(formErrors, `hex-${i}`)}
                </div>
              ))}
              <button type="button" className="btn btn-sm" onClick={addVariant}>
                <Plus size={14} aria-hidden="true" /> Add colour
              </button>
            </div>
          </form>
        </Modal>
      ) : null}

      {deleteTarget ? (
        <Modal
          title={`Delete ${deleteTarget.name}?`}
          onClose={() => setDeleteTarget(null)}
          actions={
            <>
              <button type="button" className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>
                Cancel
              </button>
              <button type="button" className="btn btn-danger" onClick={() => void confirmDelete()}>
                Delete
              </button>
            </>
          }
        >
          <p className="muted">
            This removes <strong>{deleteTarget.name}</strong> ({deleteTarget.sku}) from the catalogue. Historical
            scans keep their recorded results.
          </p>
          {deleteError ? <div className="notice danger mt-8">{deleteError}</div> : null}
        </Modal>
      ) : null}
    </div>
  );
}
