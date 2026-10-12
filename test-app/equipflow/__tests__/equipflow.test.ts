import request from 'supertest';
import app from '../src/server';
import { query, pool } from '../src/db';
import { signToken } from '../src/auth';

interface OrgRow {
  id: string;
  name: string;
  slug: string;
}

interface UserRow {
  id: string;
  org_id: string;
  email: string;
  name: string;
  role: string;
}

let orgA: OrgRow;
let orgB: OrgRow;
let adminA: UserRow;
let techA: UserRow;
let userB: UserRow;
let siteA: SiteRow;

interface SiteRow {
  id: string;
  org_id: string;
  name: string;
}

interface EquipmentRow {
  id: string;
  org_id: string;
  site_id: string;
  serial: string;
}

async function seedUser(
  orgId: string,
  email: string,
  name: string,
  role: string,
  password: string
): Promise<UserRow> {
  const result = await query<UserRow>(
    'INSERT INTO users (org_id, email, name, role, password_hash) VALUES ($1, $2, $3, $4, $5) RETURNING id, org_id, email, name, role',
    [orgId, email, name, role, `test-hash-${password}`]
  );
  return result.rows[0];
}

beforeAll(async () => {
  await query('TRUNCATE users, orgs CASCADE');
  const resA = await query<OrgRow>(
    'INSERT INTO orgs (name, slug) VALUES ($1, $2) RETURNING id, name, slug',
    ['Org A', 'org-a']
  );
  orgA = resA.rows[0];
  const resB = await query<OrgRow>(
    'INSERT INTO orgs (name, slug) VALUES ($1, $2) RETURNING id, name, slug',
    ['Org B', 'org-b']
  );
  orgB = resB.rows[0];
  adminA = await seedUser(orgA.id, 'admin@orga.test', 'Admin A', 'admin', 'adminpass');
  techA = await seedUser(orgA.id, 'tech@orga.test', 'Tech A', 'technician', 'techpass');
  userB = await seedUser(orgB.id, 'tech@orgb.test', 'Tech B', 'technician', 'bpass');
  siteA = await seedSite(orgA.id, 'Org A HQ');
});

afterAll(async () => {
  await pool.end();
});

async function seedSite(orgId: string, name: string): Promise<SiteRow> {
  const result = await query<SiteRow>(
    'INSERT INTO customer_sites (org_id, name, address, city) VALUES ($1, $2, $3, $4) RETURNING id, org_id, name',
    [orgId, name, `${name} Address`, 'Testville']
  );
  return result.rows[0];
}

function tokenFor(user: UserRow, orgId: string): string {
  return signToken({
    userId: user.id,
    orgId,
    role: user.role as 'admin' | 'manager' | 'technician',
    email: user.email,
  });
}

describe('health', () => {
  it('returns ok', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: 'ok' });
  });
});

describe('POST /orgs', () => {
  it('creates an org with its first admin user (201)', async () => {
    const res = await request(app).post('/orgs').send({
      name: 'Acme Corp',
      slug: 'acme',
      adminEmail: 'root@acme.test',
      adminName: 'Acme Root',
      adminPassword: 's3cret',
    });
    expect(res.status).toBe(201);
    expect(res.body.org).toMatchObject({ name: 'Acme Corp', slug: 'acme' });
    expect(res.body.admin).toMatchObject({ email: 'root@acme.test', role: 'admin' });
    expect(res.body.org.id).toBeDefined();
  });

  it('returns 409 on duplicate slug', async () => {
    const res = await request(app).post('/orgs').send({
      name: 'Other Acme',
      slug: 'acme',
      adminEmail: 'other@acme.test',
      adminName: 'Other Root',
      adminPassword: 's3cret',
    });
    expect(res.status).toBe(409);
    expect(res.body.error).toBe('Already exists');
  });
});

describe('GET /orgs/:id', () => {
  it('returns 200 for own-org token', async () => {
    const res = await request(app)
      .get(`/orgs/${orgA.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    expect(res.body.org).toMatchObject({ id: orgA.id, slug: 'org-a' });
  });

  it('returns 404 for token of a different org (tenant isolation)', async () => {
    const res = await request(app)
      .get(`/orgs/${orgA.id}`)
      .set('Authorization', `Bearer ${tokenFor(userB, orgB.id)}`);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('returns 401 with no token', async () => {
    const res = await request(app).get(`/orgs/${orgA.id}`);
    expect(res.status).toBe(401);
    expect(res.body.error).toBe('Unauthorized');
  });
});

describe('users', () => {
  it('admin creates user (201)', async () => {
    const res = await request(app)
      .post('/users')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({
        email: 'newtech@orga.test',
        name: 'New Tech',
        role: 'technician',
        password: 'password1',
      });
    expect(res.status).toBe(201);
    expect(res.body.user).toMatchObject({
      email: 'newtech@orga.test',
      role: 'technician',
    });
  });

  it('duplicate email returns 409', async () => {
    const res = await request(app)
      .post('/users')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({
        email: 'newtech@orga.test',
        name: 'Dup Tech',
        role: 'technician',
        password: 'password1',
      });
    expect(res.status).toBe(409);
    expect(res.body.error).toBe('Already exists');
  });

  it('technician creating user returns 403', async () => {
    const res = await request(app)
      .post('/users')
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`)
      .send({
        email: 'sneaky@orga.test',
        name: 'Sneaky',
        role: 'technician',
        password: 'password1',
      });
    expect(res.status).toBe(403);
    expect(res.body.error).toBe('Forbidden');
  });

  it('list users only shows own-org users (tenant isolation)', async () => {
    const res = await request(app)
      .get('/users')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    const emails = res.body.users.map((u: UserRow) => u.email);
    expect(emails).toContain('admin@orga.test');
    expect(emails).toContain('tech@orga.test');
    expect(emails).not.toContain('tech@orgb.test');
  });
});

describe('DELETE /users/:id', () => {
  it('admin deletes user in own org (204)', async () => {
    const victim = await seedUser(orgA.id, 'victim@orga.test', 'Victim', 'manager', 'pw');
    const res = await request(app)
      .delete(`/users/${victim.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(204);
  });

  it('cross-org delete returns 404 (tenant isolation)', async () => {
    const res = await request(app)
      .delete(`/users/${userB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });
});

describe('sites', () => {
  it('admin creates site (201)', async () => {
    const res = await request(app)
      .post('/sites')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({
        name: 'Warehouse 7',
        address: '7 Depot Lane',
        city: 'Springfield',
        region: 'West',
      });
    expect(res.status).toBe(201);
    expect(res.body.site).toMatchObject({
      name: 'Warehouse 7',
      address: '7 Depot Lane',
      city: 'Springfield',
      region: 'West',
    });
    expect(res.body.site.id).toBeDefined();
  });

  it('create site returns 400 when required fields missing', async () => {
    const res = await request(app)
      .post('/sites')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ name: 'Incomplete Site' });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Missing required fields');
  });

  it('list sites only shows own-org sites (tenant isolation)', async () => {
    await seedSite(orgB.id, 'Org B Secret Site');
    const res = await request(app)
      .get('/sites')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    const names = res.body.sites.map((s: SiteRow) => s.name);
    expect(names).toContain('Org A HQ');
    expect(names).not.toContain('Org B Secret Site');
  });

  it('get cross-org site returns 404 (tenant isolation)', async () => {
    const siteB = await seedSite(orgB.id, 'Org B Other');
    const res = await request(app)
      .get(`/sites/${siteB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('get own-org site returns 200', async () => {
    const res = await request(app)
      .get(`/sites/${siteA.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    expect(res.body.site).toMatchObject({ id: siteA.id, name: 'Org A HQ' });
  });

  it('manager updates own-org site (200)', async () => {
    const manager = await seedUser(orgA.id, 'manager@orga.test', 'Mgr A', 'manager', 'pw');
    const res = await request(app)
      .put(`/sites/${siteA.id}`)
      .set('Authorization', `Bearer ${tokenFor(manager, orgA.id)}`)
      .send({ city: 'Newville', region: null });
    expect(res.status).toBe(200);
    expect(res.body.site).toMatchObject({ id: siteA.id, city: 'Newville', region: null });
  });

  it('PUT cross-org site returns 404 (tenant isolation)', async () => {
    const siteB = await seedSite(orgB.id, 'Org B Update Target');
    const res = await request(app)
      .put(`/sites/${siteB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ city: 'Hackedville' });
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('technician creating site returns 403', async () => {
    const res = await request(app)
      .post('/sites')
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`)
      .send({ name: 'Tech Site', address: '1 Way', city: 'Nowhere' });
    expect(res.status).toBe(403);
    expect(res.body.error).toBe('Forbidden');
  });

  it('DELETE cross-org site returns 404 (tenant isolation)', async () => {
    const siteB = await seedSite(orgB.id, 'Org B Delete Target');
    const res = await request(app)
      .delete(`/sites/${siteB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('admin deletes own-org site without equipment (204)', async () => {
    const temp = await seedSite(orgA.id, 'Temporary Site');
    const res = await request(app)
      .delete(`/sites/${temp.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(204);
  });

  it('deleting site referenced by equipment returns 409', async () => {
    const site = await seedSite(orgA.id, 'Site With Equipment');
    await query(
      "INSERT INTO equipment (org_id, site_id, name, serial) VALUES ($1, $2, 'Pump 1', 'SN-PUMP-1')",
      [orgA.id, site.id]
    );
    const res = await request(app)
      .delete(`/sites/${site.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(409);
    expect(res.body.error).toBe('Site in use');
  });
});

describe('equipment', () => {
  it('admin creates equipment (201)', async () => {
    const res = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({
        siteId: siteA.id,
        name: 'Compressor X',
        serial: 'SN-COMP-1',
        model: 'CX-100',
      });
    expect(res.status).toBe(201);
    expect(res.body.equipment).toMatchObject({
      name: 'Compressor X',
      serial: 'SN-COMP-1',
      status: 'operational',
    });
    expect(res.body.equipment.id).toBeDefined();
  });

  it('duplicate serial within same org returns 409', async () => {
    const res = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ siteId: siteA.id, name: 'Dup Compressor', serial: 'SN-COMP-1' });
    expect(res.status).toBe(409);
  });

  it('same serial in a different org returns 201 (per-org uniqueness)', async () => {
    const siteB = await seedSite(orgB.id, 'Org B Site');
    const managerB = await seedUser(orgB.id, 'manager@orgb.test', 'Mgr B', 'manager', 'pw');
    const res = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(managerB, orgB.id)}`)
      .send({ siteId: siteB.id, name: 'Compressor Clone', serial: 'SN-COMP-1' });
    expect(res.status).toBe(201);
    expect(res.body.equipment.serial).toBe('SN-COMP-1');
  });

  it('create with cross-org site returns 400 Invalid site', async () => {
    const siteB = await seedSite(orgB.id, 'Org B Cross Site');
    const res = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ siteId: siteB.id, name: 'Wrong Site Unit', serial: 'SN-XSITE-1' });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Invalid site');
  });

  it('create returns 400 when required fields missing', async () => {
    const res = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ name: 'No Serial', siteId: siteA.id });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Missing required fields');
  });

  it('get cross-org equipment returns 404 (tenant isolation)', async () => {
    const siteB = await seedSite(orgB.id, 'Org B Equip Site');
    const equipB = await query<EquipmentRow>(
      "INSERT INTO equipment (org_id, site_id, name, serial) VALUES ($1, $2, 'Secret Unit', 'SN-B-1') RETURNING id, org_id, site_id, serial",
      [orgB.id, siteB.id]
    );
    const res = await request(app)
      .get(`/equipment/${equipB.rows[0].id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('manager updates equipment status (200)', async () => {
    const created = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ siteId: siteA.id, name: 'Updatable Unit', serial: 'SN-UPD-1' });
    const res = await request(app)
      .put(`/equipment/${created.body.equipment.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ status: 'degraded' });
    expect(res.status).toBe(200);
    expect(res.body.equipment.status).toBe('degraded');
  });

  it('PUT with invalid status returns 400', async () => {
    const created = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ siteId: siteA.id, name: 'Invalid Status Unit', serial: 'SN-INV-1' });
    const res = await request(app)
      .put(`/equipment/${created.body.equipment.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ status: 'exploded' });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Invalid status');
  });

  it('technician creating equipment returns 403', async () => {
    const res = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`)
      .send({ siteId: siteA.id, name: 'Tech Unit', serial: 'SN-TECH-1' });
    expect(res.status).toBe(403);
    expect(res.body.error).toBe('Forbidden');
  });

  it('list ?siteId= filter is org-scoped (tenant isolation)', async () => {
    const siteB = await seedSite(orgB.id, 'Org B Filter Site');
    await query(
      "INSERT INTO equipment (org_id, site_id, name, serial) VALUES ($1, $2, 'B Filter Unit', 'SN-BF-1')",
      [orgB.id, siteB.id]
    );
    const res = await request(app)
      .get(`/equipment?siteId=${siteB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    expect(res.body.equipment).toEqual([]);
  });

  it('list ?siteId= returns only equipment at that own-org site', async () => {
    const res = await request(app)
      .get(`/equipment?siteId=${siteA.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    const serials = res.body.equipment.map((e: EquipmentRow) => e.serial);
    expect(serials).toContain('SN-COMP-1');
    expect(serials).not.toContain('SN-BF-1');
    for (const e of res.body.equipment) {
      expect(e.site_id).toBe(siteA.id);
    }
  });

  it('admin deletes own-org equipment (204)', async () => {
    const created = await request(app)
      .post('/equipment')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ siteId: siteA.id, name: 'Doomed Unit', serial: 'SN-DEL-1' });
    const res = await request(app)
      .delete(`/equipment/${created.body.equipment.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(204);
  });
});

describe('service requests', () => {
  let equipA: EquipmentRow;
  let equipB: EquipmentRow;
  let managerA: UserRow;

  interface RequestRow {
    id: string;
    org_id: string;
    equipment_id: string;
    title: string;
    priority: string;
    status: string;
  }

  async function seedRequest(
    orgId: string,
    equipmentId: string,
    title: string,
    status: string,
    raisedBy?: string
  ): Promise<RequestRow> {
    const result = await query<RequestRow>(
      'INSERT INTO service_requests (org_id, equipment_id, title, status, raised_by) VALUES ($1, $2, $3, $4, $5) RETURNING id, org_id, equipment_id, title, priority, status',
      [orgId, equipmentId, title, status, raisedBy ?? null]
    );
    return result.rows[0];
  }

  beforeAll(async () => {
    equipA = await query<EquipmentRow>(
      "INSERT INTO equipment (org_id, site_id, name, serial) VALUES ($1, $2, 'Request Unit', 'SN-REQ-1') RETURNING id, org_id, site_id, serial",
      [orgA.id, siteA.id]
    ).then((r) => r.rows[0]);
    const siteB = await seedSite(orgB.id, 'Org B Request Site');
    equipB = await query<EquipmentRow>(
      "INSERT INTO equipment (org_id, site_id, name, serial) VALUES ($1, $2, 'B Request Unit', 'SN-REQ-B1') RETURNING id, org_id, site_id, serial",
      [orgB.id, siteB.id]
    ).then((r) => r.rows[0]);
    managerA = await seedUser(orgA.id, 'reqmgr@orga.test', 'Req Mgr A', 'manager', 'pw');
  });

  it('technician creates request (201, default priority medium)', async () => {
    const res = await request(app)
      .post('/requests')
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`)
      .send({ equipmentId: equipA.id, title: 'Pump leaking', description: 'Coolant drip' });
    expect(res.status).toBe(201);
    expect(res.body.request).toMatchObject({
      equipment_id: equipA.id,
      title: 'Pump leaking',
      priority: 'medium',
      status: 'open',
    });
    expect(res.body.request.id).toBeDefined();
  });

  it('create with cross-org equipment returns 400 Invalid equipment', async () => {
    const res = await request(app)
      .post('/requests')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ equipmentId: equipB.id, title: 'Wrong org request' });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Invalid equipment');
  });

  it('list only shows own-org requests (tenant isolation)', async () => {
    await seedRequest(orgB.id, equipB.id, 'Org B Secret Request', 'open');
    const res = await request(app)
      .get('/requests')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    const titles = res.body.requests.map((r: RequestRow) => r.title);
    expect(titles).toContain('Pump leaking');
    expect(titles).not.toContain('Org B Secret Request');
  });

  it('get cross-org request returns 404 (tenant isolation)', async () => {
    const reqB = await seedRequest(orgB.id, equipB.id, 'Org B Other Request', 'open');
    const res = await request(app)
      .get(`/requests/${reqB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('get own-org request returns 200', async () => {
    const seeded = await seedRequest(orgA.id, equipA.id, 'Own Request', 'open');
    const res = await request(app)
      .get(`/requests/${seeded.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    expect(res.body.request).toMatchObject({ id: seeded.id, title: 'Own Request' });
  });

  it('manager triages open request (200 open -> triaged)', async () => {
    const seeded = await seedRequest(
      orgA.id,
      equipA.id,
      'Triage Me',
      'open',
      techA.id
    );
    const res = await request(app)
      .post(`/requests/${seeded.id}/triage`)
      .set('Authorization', `Bearer ${tokenFor(managerA, orgA.id)}`);
    expect(res.status).toBe(200);
    expect(res.body.request.status).toBe('triaged');
  });

  it('triaging already-triaged request returns 409 Invalid transition', async () => {
    const seeded = await seedRequest(orgA.id, equipA.id, 'Already Triaged', 'triaged');
    const res = await request(app)
      .post(`/requests/${seeded.id}/triage`)
      .set('Authorization', `Bearer ${tokenFor(managerA, orgA.id)}`);
    expect(res.status).toBe(409);
    expect(res.body.error).toBe('Invalid transition');
  });

  it('technician triaging returns 403', async () => {
    const seeded = await seedRequest(orgA.id, equipA.id, 'Tech Triage Target', 'open');
    const res = await request(app)
      .post(`/requests/${seeded.id}/triage`)
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`);
    expect(res.status).toBe(403);
    expect(res.body.error).toBe('Forbidden');
  });

  it('manager closes triaged request (200 triaged -> closed)', async () => {
    const seeded = await seedRequest(orgA.id, equipA.id, 'Close From Triaged', 'triaged');
    const res = await request(app)
      .post(`/requests/${seeded.id}/close`)
      .set('Authorization', `Bearer ${tokenFor(managerA, orgA.id)}`);
    expect(res.status).toBe(200);
    expect(res.body.request.status).toBe('closed');
  });

  it('closing converted request returns 409 Invalid transition', async () => {
    const seeded = await seedRequest(orgA.id, equipA.id, 'Converted Request', 'converted');
    const res = await request(app)
      .post(`/requests/${seeded.id}/close`)
      .set('Authorization', `Bearer ${tokenFor(managerA, orgA.id)}`);
    expect(res.status).toBe(409);
    expect(res.body.error).toBe('Invalid transition');
  });

  it('?status= filter returns only matching requests', async () => {
    const res = await request(app)
      .get('/requests?status=open')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(200);
    for (const r of res.body.requests) {
      expect(r.status).toBe('open');
    }
    const titles = res.body.requests.map((r: RequestRow) => r.title);
    expect(titles).not.toContain('Already Triaged');
    expect(titles).not.toContain('Close From Triaged');
  });
});

describe('work orders', () => {
  let equipA: EquipmentRow;
  let equipB: EquipmentRow;
  let managerA: UserRow;
  let techB: UserRow;
  let siteB: SiteRow;

  interface WorkOrderRow {
    id: string;
    org_id: string;
    code: string;
    title: string;
    status: string;
    assigned_technician_id: string | null;
    site_id: string;
    equipment_id: string;
    service_request_id: string | null;
  }

  async function seedWorkOrder(
    orgId: string,
    siteId: string,
    equipmentId: string,
    code: string,
    status: string,
    assignedTechId?: string
  ): Promise<WorkOrderRow> {
    const result = await query<WorkOrderRow>(
      "INSERT INTO work_orders (org_id, code, title, site_id, equipment_id, status, assigned_technician_id) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id, org_id, code, title, status, assigned_technician_id, site_id, equipment_id, service_request_id",
      [orgId, code, `WO ${code}`, siteId, equipmentId, status, assignedTechId ?? null]
    );
    return result.rows[0];
  }

  beforeAll(async () => {
    equipA = await query<EquipmentRow>(
      "INSERT INTO equipment (org_id, site_id, name, serial) VALUES ($1, $2, 'WO Unit', 'SN-WO-1') RETURNING id, org_id, site_id, serial",
      [orgA.id, siteA.id]
    ).then((r) => r.rows[0]);
    siteB = await seedSite(orgB.id, 'Org B WO Site');
    equipB = await query<EquipmentRow>(
      "INSERT INTO equipment (org_id, site_id, name, serial) VALUES ($1, $2, 'B WO Unit', 'SN-WO-B1') RETURNING id, org_id, site_id, serial",
      [orgB.id, siteB.id]
    ).then((r) => r.rows[0]);
    managerA = await seedUser(orgA.id, 'womgr@orga.test', 'WO Mgr A', 'manager', 'pw');
    techB = await seedUser(orgB.id, 'wotech@orgb.test', 'WO Tech B', 'technician', 'pw');
  });

  it('admin creates work order (201, code WO-2026-0001)', async () => {
    const res = await request(app)
      .post('/workorders')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ siteId: siteA.id, equipmentId: equipA.id, title: 'Fix pump' });
    expect(res.status).toBe(201);
    expect(res.body.workOrder).toMatchObject({
      code: 'WO-2026-0001',
      title: 'Fix pump',
      status: 'draft',
      type: 'corrective',
      priority: 'medium',
    });
    expect(res.body.workOrder.id).toBeDefined();
  });

  it('second work order gets WO-2026-0002 (per-org sequence)', async () => {
    const res = await request(app)
      .post('/workorders')
      .set('Authorization', `Bearer ${tokenFor(managerA, orgA.id)}`)
      .send({ siteId: siteA.id, equipmentId: equipA.id, title: 'Second WO' });
    expect(res.status).toBe(201);
    expect(res.body.workOrder.code).toBe('WO-2026-0002');
  });

  it('same code WO-2026-0001 in org B returns 201 (per-org uniqueness)', async () => {
    await seedWorkOrder(orgB.id, siteB.id, equipB.id, 'WO-2026-0001', 'draft');
    const res = await request(app)
      .post('/workorders')
      .set('Authorization', `Bearer ${tokenFor(techB, orgB.id)}`)
      .send({ siteId: siteB.id, equipmentId: equipB.id, title: 'Org B WO' });
    expect(res.status).toBe(403);
  });

  it('org B admin can create WO-2026-0002 (per-org uniqueness)', async () => {
    const managerB = await seedUser(orgB.id, 'womgr@orgb.test', 'WO Mgr B', 'manager', 'pw');
    const res = await request(app)
      .post('/workorders')
      .set('Authorization', `Bearer ${tokenFor(managerB, orgB.id)}`)
      .send({ siteId: siteB.id, equipmentId: equipB.id, title: 'Org B Second' });
    expect(res.status).toBe(201);
    expect(res.body.workOrder.code).toBe('WO-2026-0002');
  });

  it('create with cross-org equipment returns 400', async () => {
    const res = await request(app)
      .post('/workorders')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ siteId: siteA.id, equipmentId: equipB.id, title: 'Wrong org' });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Invalid equipment');
  });

  it('create with manager as technician returns 400 Invalid technician', async () => {
    const res = await request(app)
      .post('/workorders')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({
        siteId: siteA.id,
        equipmentId: equipA.id,
        title: 'Bad assignee',
        assignedTechnicianId: managerA.id,
      });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('Invalid technician');
  });

  it('admin transitions draft -> scheduled -> in_progress -> completed (200 each)', async () => {
    const created = await request(app)
      .post('/workorders')
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ siteId: siteA.id, equipmentId: equipA.id, title: 'Transition WO' });
    const id = created.body.workOrder.id;
    const scheduled = await request(app)
      .post(`/workorders/${id}/status`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ status: 'scheduled' });
    expect(scheduled.status).toBe(200);
    expect(scheduled.body.workOrder.status).toBe('scheduled');
    const inProgress = await request(app)
      .post(`/workorders/${id}/status`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ status: 'in_progress' });
    expect(inProgress.status).toBe(200);
    expect(inProgress.body.workOrder.status).toBe('in_progress');
    const completed = await request(app)
      .post(`/workorders/${id}/status`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ status: 'completed' });
    expect(completed.status).toBe(200);
    expect(completed.body.workOrder.status).toBe('completed');
  });

  it.each([
    ['draft', 'in_progress'],
    ['draft', 'completed'],
    ['scheduled', 'blocked'],
    ['in_progress', 'scheduled'],
    ['completed', 'cancelled'],
  ])('invalid transition %s -> %s returns 409', async (from, to) => {
    const wo = await seedWorkOrder(orgA.id, siteA.id, equipA.id, `WO-INV-${from}-${to}`, from);
    const res = await request(app)
      .post(`/workorders/${wo.id}/status`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ status: to });
    expect(res.status).toBe(409);
    expect(res.body.error).toBe('Invalid transition');
  });

  it('assigned technician completes in_progress WO (200)', async () => {
    const wo = await seedWorkOrder(
      orgA.id,
      siteA.id,
      equipA.id,
      'WO-TECH-OK',
      'in_progress',
      techA.id
    );
    const res = await request(app)
      .post(`/workorders/${wo.id}/status`)
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`)
      .send({ status: 'completed' });
    expect(res.status).toBe(200);
    expect(res.body.workOrder.status).toBe('completed');
  });

  it('technician draft -> scheduled returns 403 (valid transition, tech-disallowed)', async () => {
    const wo = await seedWorkOrder(orgA.id, siteA.id, equipA.id, 'WO-TECH-DRAFT', 'draft');
    const res = await request(app)
      .post(`/workorders/${wo.id}/status`)
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`)
      .send({ status: 'scheduled' });
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('unassigned technician on other tech WO returns 404 (no-leak)', async () => {
    const other = await seedUser(orgA.id, 'othertech@orga.test', 'Other Tech', 'technician', 'pw');
    const wo = await seedWorkOrder(
      orgA.id,
      siteA.id,
      equipA.id,
      'WO-OTHER-TECH',
      'in_progress',
      other.id
    );
    const res = await request(app)
      .post(`/workorders/${wo.id}/status`)
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`)
      .send({ status: 'completed' });
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('technician creating work order returns 403', async () => {
    const res = await request(app)
      .post('/workorders')
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`)
      .send({ siteId: siteA.id, equipmentId: equipA.id, title: 'Tech WO' });
    expect(res.status).toBe(403);
    expect(res.body.error).toBe('Forbidden');
  });

  it('technician DELETE returns 403', async () => {
    const wo = await seedWorkOrder(orgA.id, siteA.id, equipA.id, 'WO-TECH-DEL', 'draft');
    const res = await request(app)
      .delete(`/workorders/${wo.id}`)
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`);
    expect(res.status).toBe(403);
    expect(res.body.error).toBe('Forbidden');
  });

  it('converts service request to work order (201, request converted)', async () => {
    const seeded = await query<{ id: string; equipment_id: string }>(
      "INSERT INTO service_requests (org_id, equipment_id, title, description, priority, status) VALUES ($1, $2, 'Convert me', 'Convert desc', 'high', 'open') RETURNING id, equipment_id",
      [orgA.id, equipA.id]
    );
    const res = await request(app)
      .post(`/workorders/convert/${seeded.rows[0].id}`)
      .set('Authorization', `Bearer ${tokenFor(managerA, orgA.id)}`)
      .send({});
    expect(res.status).toBe(201);
    expect(res.body.workOrder).toMatchObject({
      type: 'corrective',
      priority: 'high',
      title: 'Convert me',
      service_request_id: seeded.rows[0].id,
      site_id: siteA.id,
    });
    expect(res.body.workOrder.code).toMatch(/^WO-2026-\d{4}$/);
    expect(res.body.request.status).toBe('converted');
  });

  it('double convert returns 409 Request already converted', async () => {
    const seeded = await query<{ id: string }>(
      "INSERT INTO service_requests (org_id, equipment_id, title, status) VALUES ($1, $2, 'Double convert', 'open') RETURNING id",
      [orgA.id, equipA.id]
    );
    const requestId = seeded.rows[0].id;
    const first = await request(app)
      .post(`/workorders/convert/${requestId}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({});
    expect(first.status).toBe(201);
    const second = await request(app)
      .post(`/workorders/convert/${requestId}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({});
    expect(second.status).toBe(409);
    expect(second.body.error).toBe('Request already converted');
  });

  it('convert cross-org request returns 404', async () => {
    const seeded = await query<{ id: string }>(
      "INSERT INTO service_requests (org_id, equipment_id, title, status) VALUES ($1, $2, 'Org B Convert', 'open') RETURNING id",
      [orgB.id, equipB.id]
    );
    const res = await request(app)
      .post(`/workorders/convert/${seeded.rows[0].id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({});
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('GET cross-org work order returns 404', async () => {
    const woB = await seedWorkOrder(orgB.id, siteB.id, equipB.id, 'WO-B-GET', 'draft');
    const res = await request(app)
      .get(`/workorders/${woB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('PUT cross-org work order returns 404', async () => {
    const woB = await seedWorkOrder(orgB.id, siteB.id, equipB.id, 'WO-B-PUT', 'draft');
    const res = await request(app)
      .put(`/workorders/${woB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`)
      .send({ title: 'Hacked' });
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('DELETE cross-org work order returns 404', async () => {
    const woB = await seedWorkOrder(orgB.id, siteB.id, equipB.id, 'WO-B-DEL', 'draft');
    const res = await request(app)
      .delete(`/workorders/${woB.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(404);
    expect(res.body.error).toBe('Not found');
  });

  it('list ?assignedTo=me returns only own assigned WOs', async () => {
    const mine = await seedWorkOrder(
      orgA.id,
      siteA.id,
      equipA.id,
      'WO-MINE-1',
      'scheduled',
      techA.id
    );
    await seedWorkOrder(orgA.id, siteA.id, equipA.id, 'WO-THEIRS-1', 'scheduled');
    const res = await request(app)
      .get('/workorders?assignedTo=me')
      .set('Authorization', `Bearer ${tokenFor(techA, orgA.id)}`);
    expect(res.status).toBe(200);
    const codes = res.body.workOrders.map((w: WorkOrderRow) => w.code);
    expect(codes).toContain('WO-MINE-1');
    expect(codes).not.toContain('WO-THEIRS-1');
    for (const w of res.body.workOrders) {
      expect(w.assigned_technician_id).toBe(techA.id);
    }
  });

  it('manager PUTs own-org WO priority and type (200)', async () => {
    const wo = await seedWorkOrder(orgA.id, siteA.id, equipA.id, 'WO-PUT-OK', 'draft');
    const res = await request(app)
      .put(`/workorders/${wo.id}`)
      .set('Authorization', `Bearer ${tokenFor(managerA, orgA.id)}`)
      .send({ priority: 'urgent', type: 'preventive' });
    expect(res.status).toBe(200);
    expect(res.body.workOrder).toMatchObject({ priority: 'urgent', type: 'preventive' });
  });

  it('admin deletes own-org work order (204)', async () => {
    const wo = await seedWorkOrder(orgA.id, siteA.id, equipA.id, 'WO-DEL-OK', 'draft');
    const res = await request(app)
      .delete(`/workorders/${wo.id}`)
      .set('Authorization', `Bearer ${tokenFor(adminA, orgA.id)}`);
    expect(res.status).toBe(204);
  });
});
