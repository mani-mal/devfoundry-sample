import { createConfigCommand } from '../src/commands/config';
import { createSkillCommand } from '../src/commands/skill';
import * as fs from 'fs';
import * as path from 'path';
import type { Command } from 'commander';

const TEST_DIR = path.join('/tmp', 'opencode', 'cli-config-test');

describe('config command', () => {
  let originalCwd: string;

  beforeAll(() => {
    originalCwd = process.cwd();
    fs.mkdirSync(TEST_DIR, { recursive: true });
  });

  afterAll(() => {
    process.chdir(originalCwd);
    fs.rmSync(TEST_DIR, { recursive: true, force: true });
  });

  beforeEach(() => {
    process.chdir(TEST_DIR);
    fs.rmSync(path.join(TEST_DIR, '.devfoundry'), { recursive: true, force: true });
    delete process.env.DEVFOUNDRY_MODEL_ROUTE;
  });

  const parse = (cmd: Command, args: string[]) => {
    cmd.exitOverride();
    cmd.parse(args, { from: 'user' });
  };

  it('should set and persist a value', () => {
    const out: string[] = [];
    jest.spyOn(console, 'log').mockImplementation((m: string) => out.push(m));
    parse(createConfigCommand(), ['set', 'capacityProfile', 'gpu-heavy']);
    jest.restoreAllMocks();

    const config = JSON.parse(fs.readFileSync(path.join(TEST_DIR, '.devfoundry', 'config.json'), 'utf8'));
    expect(config.capacityProfile).toBe('gpu-heavy');
    expect(out.join('\n')).toContain('Set capacityProfile=');
    expect(out.join('\n')).toContain('Persisted to');
  });

  it('should get a persisted value', () => {
    fs.mkdirSync(path.join(TEST_DIR, '.devfoundry'), { recursive: true });
    fs.writeFileSync(
      path.join(TEST_DIR, '.devfoundry', 'config.json'),
      JSON.stringify({ capacityProfile: 'gpu-heavy' })
    );
    const out: string[] = [];
    jest.spyOn(console, 'log').mockImplementation((m: string) => out.push(m));
    parse(createConfigCommand(), ['get', 'capacityProfile']);
    jest.restoreAllMocks();
    expect(out[0]).toBe('gpu-heavy');
  });

  it('should fall back to env for get', () => {
    process.env.DEVFOUNDRY_MODEL_ROUTE = 'local-fast';
    const out: string[] = [];
    jest.spyOn(console, 'log').mockImplementation((m: string) => out.push(m));
    parse(createConfigCommand(), ['get', 'model.route']);
    jest.restoreAllMocks();
    expect(out[0]).toBe('local-fast');
    delete process.env.DEVFOUNDRY_MODEL_ROUTE;
  });

  it('should list persisted keys', () => {
    fs.mkdirSync(path.join(TEST_DIR, '.devfoundry'), { recursive: true });
    fs.writeFileSync(
      path.join(TEST_DIR, '.devfoundry', 'config.json'),
      JSON.stringify({ a: '1', b: '2' })
    );
    const out: string[] = [];
    jest.spyOn(console, 'log').mockImplementation((m: string) => out.push(m));
    parse(createConfigCommand(), ['list']);
    jest.restoreAllMocks();
    expect(out.join('\n')).toContain('a=1');
    expect(out.join('\n')).toContain('b=2');
  });
});

describe('skill command', () => {
  it('should have list and install subcommands', () => {
    const skill = createSkillCommand();
    const names = skill.commands.map((c) => c.name());
    expect(names).toContain('list');
    expect(names).toContain('install');
  });

  it('should install with default options and report the digest', async () => {
    const mockDb = {
      getDatabase: () => ({
        pool: {
          connect: async () => ({
            query: async (text: string, params?: unknown[]) => {
              expect(text).toContain('INSERT INTO skills');
              expect(params?.[1]).toMatch(/^[0-9a-f]{64}$/);
              expect(params?.[2]).toBe('version-control');
              return { rows: [{ id: 'skill-1', name: 'version-control', version: '2.0.0', approval_status: 'approved' }] };
            },
            release: () => {},
          }),
        },
      }),
    };
    const out: string[] = [];
    jest.spyOn(console, 'log').mockImplementation((m: string) => out.push(m));

    const skill = createSkillCommand(mockDb as never);
    skill.exitOverride();
    await skill.parseAsync(['install', 'version-control', '--version', '2.0.0', '--status', 'approved'], { from: 'user' });
    jest.restoreAllMocks();

    expect(out.join('\n')).toContain('Skill installed: version-control@2.0.0 (approved)');
    expect(out.join('\n')).toContain('digest=');
  });

  it('should error when no database is configured', async () => {
    const errSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const exitSpy = jest.spyOn(process, 'exit').mockImplementation(((code?: number) => {
      throw new Error(`exit ${code}`);
    }) as never);

    const skill = createSkillCommand();
    skill.exitOverride();
    await expect(
      skill.parseAsync(['install', 'some-skill'], { from: 'user' })
    ).rejects.toThrow('exit 1');

    jest.restoreAllMocks();
    expect(errSpy).toHaveBeenCalled();
  });
});
