import { useState, useEffect } from 'react';
import { Card, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Textarea } from '../components/ui/Textarea';
import { Select } from '../components/ui/Select';
import { apiClient } from '../lib/api';
import {
  BrainCircuit,
  Boxes,
  Plus,
  Edit,
  Trash2,
  KeyRound,
  Shield,
  Copy,
  CheckCircle,
  X
} from 'lucide-react';

interface OnboardModelForm {
  slug: string;
  displayName: string;
  tier: string;
  endpoint: string;
  priceInput: string;
  priceOutput: string;
  contextWindow: string;
  notes: string;
}

interface ApplicationForm {
  id: string;
  name: string;
  ownerEmail: string;
}

interface PolicyForm {
  allowedTiers: string;
  allowedProviders: string;
  allowedModels: string;
  residency: string;
  maxSpendUsdPerDay: string;
  maxCostUsdPerRequest: string;
}

const emptyModelForm: OnboardModelForm = {
  slug: '',
  displayName: '',
  tier: 'mid',
  endpoint: '',
  priceInput: '',
  priceOutput: '',
  contextWindow: '',
  notes: '',
};

const emptyAppForm: ApplicationForm = { id: '', name: '', ownerEmail: '' };

const emptyPolicyForm: PolicyForm = {
  allowedTiers: '',
  allowedProviders: '',
  allowedModels: '',
  residency: 'any',
  maxSpendUsdPerDay: '',
  maxCostUsdPerRequest: '',
};

const splitList = (value: string) =>
  value
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);

const omitEmpty = (obj: Record<string, unknown>) =>
  Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== ''));

export default function ModelGateway() {
  const [models, setModels] = useState<any[]>([]);
  const [applications, setApplications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showModelForm, setShowModelForm] = useState(false);
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [modelForm, setModelForm] = useState<OnboardModelForm>(emptyModelForm);
  const [showAppForm, setShowAppForm] = useState(false);
  const [appForm, setAppForm] = useState<ApplicationForm>(emptyAppForm);
  const [tokenInputs, setTokenInputs] = useState<Record<string, string>>({});
  const [mintedToken, setMintedToken] = useState<{ appId: string; token: string } | null>(null);
  const [tokenCopied, setTokenCopied] = useState(false);
  const [policySlug, setPolicySlug] = useState<string | null>(null);
  const [policyForm, setPolicyForm] = useState<PolicyForm>(emptyPolicyForm);

  const reload = async () => {
    try {
      const [modelsRes, appsRes] = await Promise.all([
        apiClient.getGatewayModels(),
        apiClient.getGatewayApplications(),
      ]);
      setModels(modelsRes.models);
      setApplications(appsRes.applications);
      setLoadError(null);
    } catch (err) {
      setLoadError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  const modelBodyFrom = (m: OnboardModelForm) =>
    omitEmpty({
      slug: m.slug,
      displayName: m.displayName,
      tier: m.tier,
      endpoint: m.endpoint,
      priceInput: m.priceInput,
      priceOutput: m.priceOutput,
      contextWindow: m.contextWindow,
      notes: m.notes,
    });

  const handleModelSubmit = async () => {
    try {
      if (editingSlug) {
        await apiClient.editGatewayModel(editingSlug, modelBodyFrom(modelForm));
      } else {
        await apiClient.onboardGatewayModel(modelBodyFrom(modelForm));
      }
      setShowModelForm(false);
      setEditingSlug(null);
      setModelForm(emptyModelForm);
      setLoadError(null);
      await reload();
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const handleToggleModel = async (model: any) => {
    try {
      const body = omitEmpty({
        slug: model.slug,
        displayName: model.display_name,
        tier: model.tier,
        endpoint: model.endpoint,
        priceInput: model.price_input,
        priceOutput: model.price_output,
        priceCachedInput: model.price_cached_input,
        quality: model.quality,
        contextWindow: model.context_window,
        allowedAppIds: model.allowed_app_ids,
        notes: model.notes,
        enabled: !model.enabled,
        region: model.region,
        promptRetention: model.prompt_retention,
        acceptsRawSensitive: model.accepts_raw_sensitive,
      });
      await apiClient.editGatewayModel(model.slug, body);
      setLoadError(null);
      await reload();
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const handleEditModel = (model: any) => {
    setEditingSlug(model.slug);
    setShowModelForm(true);
    setModelForm({
      slug: model.slug ?? '',
      displayName: model.display_name ?? '',
      tier: model.tier ?? 'mid',
      endpoint: model.endpoint ?? '',
      priceInput: model.price_input != null ? String(model.price_input) : '',
      priceOutput: model.price_output != null ? String(model.price_output) : '',
      contextWindow: model.context_window != null ? String(model.context_window) : '',
      notes: model.notes ?? '',
    });
  };

  const handleDeleteModel = async (slug: string) => {
    if (!window.confirm(`Delete model "${slug}"?`)) return;
    try {
      await apiClient.deleteGatewayModel(slug);
      setLoadError(null);
      await reload();
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const handleAppSubmit = async () => {
    try {
      await apiClient.createGatewayApplication(
        omitEmpty({
          id: appForm.id,
          name: appForm.name,
          ownerEmail: appForm.ownerEmail,
        })
      );
      setShowAppForm(false);
      setAppForm(emptyAppForm);
      setLoadError(null);
      await reload();
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const handleCreateToken = async (appId: string) => {
    try {
      const res = await apiClient.createGatewayApplicationToken(appId, tokenInputs[appId] || undefined);
      const token = typeof res?.token === 'string' ? res.token : JSON.stringify(res, null, 2);
      setMintedToken({ appId, token });
      setTokenCopied(false);
      setTokenInputs((prev) => ({ ...prev, [appId]: '' }));
      setLoadError(null);
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  const handleCopyToken = async () => {
    if (!mintedToken) return;
    try {
      await navigator.clipboard.writeText(mintedToken.token);
      setTokenCopied(true);
    } catch {
      setTokenCopied(false);
    }
  };

  const handleOpenPolicy = (app: any) => {
    setPolicySlug(app.id);
    setPolicyForm({
      allowedTiers: Array.isArray(app.policy?.allowedTiers) ? app.policy.allowedTiers.join(', ') : '',
      allowedProviders: Array.isArray(app.policy?.allowedProviders) ? app.policy.allowedProviders.join(', ') : '',
      allowedModels: Array.isArray(app.policy?.allowedModels) ? app.policy.allowedModels.join(', ') : '',
      residency: app.policy?.residency ?? 'any',
      maxSpendUsdPerDay: app.policy?.maxSpendUsdPerDay != null ? String(app.policy.maxSpendUsdPerDay) : '',
      maxCostUsdPerRequest: app.policy?.maxCostUsdPerRequest != null ? String(app.policy.maxCostUsdPerRequest) : '',
    });
  };

  const handlePolicySubmit = async () => {
    if (!policySlug) return;
    try {
      const body = omitEmpty({
        allowedTiers: splitList(policyForm.allowedTiers).length ? splitList(policyForm.allowedTiers) : '',
        allowedProviders: splitList(policyForm.allowedProviders).length ? splitList(policyForm.allowedProviders) : '',
        allowedModels: splitList(policyForm.allowedModels).length ? splitList(policyForm.allowedModels) : '',
        residency: policyForm.residency === 'any' ? '' : policyForm.residency,
        maxSpendUsdPerDay: policyForm.maxSpendUsdPerDay,
        maxCostUsdPerRequest: policyForm.maxCostUsdPerRequest,
      });
      await apiClient.setGatewayPolicy(policySlug, body);
      setPolicySlug(null);
      setLoadError(null);
      await reload();
    } catch (err) {
      setLoadError((err as Error).message);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-dashboard-bg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <p className="text-dashboard-muted">Loading model gateway…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dashboard-bg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 animate-fade-in-up">
          <div>
            <h1 className="text-3xl font-bold text-dashboard-text mb-2">Model Gateway</h1>
            <p className="text-dashboard-muted">Onboard models, manage applications, and set routing policies</p>
          </div>
        </div>

        {/* Load Error */}
        {loadError && (
          <div className="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
            Gateway error: {loadError}
          </div>
        )}

        {/* Models */}
        <Card variant="elevated" className="mb-6">
          <CardContent className="p-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-dashboard-text flex items-center gap-2">
                  <BrainCircuit className="h-5 w-5 text-primary-400" />
                  Models
                </h3>
                <Button
                  variant="primary"
                  size="sm"
                  leftIcon={<Plus className="h-4 w-4" />}
                  onClick={() => {
                    setShowModelForm(!showModelForm);
                    setEditingSlug(null);
                    setModelForm(emptyModelForm);
                  }}
                >
                  Onboard Model
                </Button>
              </div>

              {showModelForm && (
                <div className="p-4 bg-dashboard-card/50 rounded-lg border border-dashboard-border/50 space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Input
                      label="Slug"
                      value={modelForm.slug}
                      onChange={(e) => setModelForm((f) => ({ ...f, slug: e.target.value }))}
                      placeholder="gpt-5"
                      disabled={editingSlug !== null}
                    />
                    <Input
                      label="Display Name"
                      value={modelForm.displayName}
                      onChange={(e) => setModelForm((f) => ({ ...f, displayName: e.target.value }))}
                      placeholder="GPT-5"
                    />
                    <Select
                      label="Tier"
                      value={modelForm.tier}
                      onChange={(e) => setModelForm((f) => ({ ...f, tier: e.target.value }))}
                    >
                      <option value="cheap">cheap</option>
                      <option value="mid">mid</option>
                      <option value="frontier">frontier</option>
                    </Select>
                    <Input
                      label="Endpoint"
                      value={modelForm.endpoint}
                      onChange={(e) => setModelForm((f) => ({ ...f, endpoint: e.target.value }))}
                      placeholder="https://api.openai.com/v1"
                    />
                    <Input
                      label="Price Input ($/M tokens)"
                      value={modelForm.priceInput}
                      onChange={(e) => setModelForm((f) => ({ ...f, priceInput: e.target.value }))}
                      placeholder="2.50"
                    />
                    <Input
                      label="Price Output ($/M tokens)"
                      value={modelForm.priceOutput}
                      onChange={(e) => setModelForm((f) => ({ ...f, priceOutput: e.target.value }))}
                      placeholder="10.00"
                    />
                    <Input
                      label="Context Window"
                      value={modelForm.contextWindow}
                      onChange={(e) => setModelForm((f) => ({ ...f, contextWindow: e.target.value }))}
                      placeholder="200000"
                    />
                    <Textarea
                      label="Notes"
                      value={modelForm.notes}
                      onChange={(e) => setModelForm((f) => ({ ...f, notes: e.target.value }))}
                      rows={2}
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="primary" size="sm" onClick={handleModelSubmit}>
                      {editingSlug ? 'Save Changes' : 'Onboard'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setShowModelForm(false);
                        setEditingSlug(null);
                        setModelForm(emptyModelForm);
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                    <tr>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Model</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Tier</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Endpoint</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Context Window</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Prices (in/out)</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Enabled</th>
                      <th className="text-right py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dashboard-border">
                    {models.length === 0 && (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-sm text-dashboard-muted">
                          No models onboarded — onboard your first model to make it available to tasks.
                        </td>
                      </tr>
                    )}
                    {models.map((model) => (
                      <tr key={model.slug} className="hover:bg-dashboard-card/30 transition-colors">
                        <td className="py-3 px-4">
                          <span className="text-sm font-medium text-dashboard-text">{model.display_name || model.slug}</span>
                          <p className="text-xs text-dashboard-muted">{model.slug}</p>
                        </td>
                        <td className="py-3 px-4">
                          <Badge variant={model.tier === 'frontier' ? 'primary' : model.tier === 'cheap' ? 'info' : 'secondary'}>
                            {model.tier || '—'}
                          </Badge>
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-sm text-dashboard-text-secondary truncate max-w-[220px] block" title={model.endpoint}>
                            {model.endpoint || '—'}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-sm text-dashboard-text-secondary">{model.context_window ?? '—'}</span>
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-sm text-dashboard-text-secondary">
                            {model.price_input ?? '—'} / {model.price_output ?? '—'}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <Badge variant={model.enabled ? 'success' : 'danger'}>
                            {model.enabled ? 'Enabled' : 'Disabled'}
                          </Badge>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Button
                              variant={model.enabled ? 'secondary' : 'primary'}
                              size="sm"
                              onClick={() => handleToggleModel(model)}
                            >
                              {model.enabled ? 'Disable' : 'Enable'}
                            </Button>
                            <Button variant="ghost" size="sm" title="Edit" onClick={() => handleEditModel(model)}>
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Delete"
                              className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                              onClick={() => handleDeleteModel(model.slug)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Applications & Tokens */}
        <Card variant="elevated">
          <CardContent className="p-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-dashboard-text flex items-center gap-2">
                  <Boxes className="h-5 w-5 text-purple-400" />
                  Applications &amp; Tokens
                </h3>
                <Button
                  variant="primary"
                  size="sm"
                  leftIcon={<Plus className="h-4 w-4" />}
                  onClick={() => setShowAppForm(!showAppForm)}
                >
                  Create Application
                </Button>
              </div>

              {showAppForm && (
                <div className="p-4 bg-dashboard-card/50 rounded-lg border border-dashboard-border/50 space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <Input
                      label="ID"
                      value={appForm.id}
                      onChange={(e) => setAppForm((f) => ({ ...f, id: e.target.value }))}
                      placeholder="my-app"
                    />
                    <Input
                      label="Name"
                      value={appForm.name}
                      onChange={(e) => setAppForm((f) => ({ ...f, name: e.target.value }))}
                      placeholder="My App"
                    />
                    <Input
                      label="Owner Email"
                      value={appForm.ownerEmail}
                      onChange={(e) => setAppForm((f) => ({ ...f, ownerEmail: e.target.value }))}
                      placeholder="owner@example.com"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="primary" size="sm" onClick={handleAppSubmit}>
                      Create
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setShowAppForm(false);
                        setAppForm(emptyAppForm);
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-dashboard-card/50 border-b border-dashboard-border">
                    <tr>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">ID</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Name</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Owner</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Status</th>
                      <th className="text-left py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Residency</th>
                      <th className="text-right py-3 px-4 text-xs font-semibold text-dashboard-muted uppercase tracking-wider">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-dashboard-border">
                    {applications.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-8 text-center text-sm text-dashboard-muted">
                          No applications registered — create an application to mint gateway tokens.
                        </td>
                      </tr>
                    )}
                    {applications.map((app) => (
                      <tr key={app.id} className="hover:bg-dashboard-card/30 transition-colors">
                        <td className="py-3 px-4">
                          <span className="text-sm font-medium text-dashboard-text">{app.id}</span>
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-sm text-dashboard-text-secondary">{app.name}</span>
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-sm text-dashboard-text-secondary truncate max-w-[200px] block" title={app.owner_email}>
                            {app.owner_email || '—'}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <Badge variant={app.status === 'active' ? 'success' : 'default'}>
                            {app.status || 'unknown'}
                          </Badge>
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-sm text-dashboard-text-secondary">{app.default_residency || 'any'}</span>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <Input
                              value={tokenInputs[app.id] || ''}
                              onChange={(e) => setTokenInputs((prev) => ({ ...prev, [app.id]: e.target.value }))}
                              placeholder="Token name"
                              containerClassName="w-40"
                            />
                            <Button
                              variant="secondary"
                              size="sm"
                              leftIcon={<KeyRound className="h-4 w-4" />}
                              onClick={() => handleCreateToken(app.id)}
                            >
                              Create Token
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              title="Policy"
                              leftIcon={<Shield className="h-4 w-4" />}
                              onClick={() => handleOpenPolicy(app)}
                            >
                              Policy
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {mintedToken && (
                <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium text-emerald-300 flex items-center gap-2">
                      <CheckCircle className="h-4 w-4" />
                      Token minted for <code>{mintedToken.appId}</code> — copy now, shown once
                    </p>
                    <div className="flex items-center gap-2">
                      <Button variant="secondary" size="xs" leftIcon={<Copy className="h-3 w-3" />} onClick={handleCopyToken}>
                        {tokenCopied ? 'Copied' : 'Copy'}
                      </Button>
                      <Button variant="ghost" size="xs" onClick={() => setMintedToken(null)}>
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                  <pre className="text-xs text-emerald-200 bg-dashboard-bg/50 rounded p-3 overflow-x-auto whitespace-pre-wrap break-all">
                    {mintedToken.token}
                  </pre>
                  <p className="text-xs text-emerald-300/70 mt-2">Copy now — shown once</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Policy Editor */}
        {policySlug && (
          <Card variant="elevated" className="mt-6">
            <CardContent className="p-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-dashboard-text flex items-center gap-2">
                    <Shield className="h-5 w-5 text-primary-400" />
                    Policy for <code className="text-primary-400">{policySlug}</code>
                  </h3>
                  <Button variant="ghost" size="sm" onClick={() => setPolicySlug(null)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Input
                    label="Allowed Tiers (comma-separated)"
                    value={policyForm.allowedTiers}
                    onChange={(e) => setPolicyForm((f) => ({ ...f, allowedTiers: e.target.value }))}
                    placeholder="cheap, mid, frontier"
                  />
                  <Input
                    label="Allowed Providers (comma-separated)"
                    value={policyForm.allowedProviders}
                    onChange={(e) => setPolicyForm((f) => ({ ...f, allowedProviders: e.target.value }))}
                    placeholder="openai, anthropic"
                  />
                  <Input
                    label="Allowed Models (comma-separated)"
                    value={policyForm.allowedModels}
                    onChange={(e) => setPolicyForm((f) => ({ ...f, allowedModels: e.target.value }))}
                    placeholder="gpt-5, claude-4"
                  />
                  <Select
                    label="Residency"
                    value={policyForm.residency}
                    onChange={(e) => setPolicyForm((f) => ({ ...f, residency: e.target.value }))}
                  >
                    <option value="any">any</option>
                    <option value="private_cloud_ok">private_cloud_ok</option>
                    <option value="onprem_only">onprem_only</option>
                  </Select>
                  <Input
                    label="Max Spend USD / Day"
                    value={policyForm.maxSpendUsdPerDay}
                    onChange={(e) => setPolicyForm((f) => ({ ...f, maxSpendUsdPerDay: e.target.value }))}
                    placeholder="100.00"
                  />
                  <Input
                    label="Max Cost USD / Request"
                    value={policyForm.maxCostUsdPerRequest}
                    onChange={(e) => setPolicyForm((f) => ({ ...f, maxCostUsdPerRequest: e.target.value }))}
                    placeholder="5.00"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="primary" size="sm" onClick={handlePolicySubmit}>
                    Save Policy
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setPolicySlug(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
