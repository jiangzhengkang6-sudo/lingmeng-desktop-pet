import { describe, expect, it, vi } from 'vitest'
import { PersonaClient, PersonaClientError } from './PersonaClient'

const draft = {
  profile_name: 'p',
  character_name: 'miya',
  personality: '嘴硬心软',
  speaking_style: '短促带哼声',
  default_action: 'idle',
  voice_id: '',
  system_prompt: '',
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const fullProfile = {
  ...draft,
  id: 'a',
  is_active: true,
  created_at: '',
  updated_at: '',
}

describe('PersonaClient', () => {
  it('lists profiles', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse([fullProfile]))
    const client = new PersonaClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    const profiles = await client.list()
    expect(profiles[0]?.id).toBe('a')
    expect(fetchImpl.mock.calls[0]?.[0]).toBe('http://127.0.0.1:8000/api/personas')
  })

  it('returns null when no persona is active', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(null))
    const client = new PersonaClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })
    expect(await client.active()).toBeNull()
  })

  it('creates a persona via POST JSON', async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ ...fullProfile, id: 'new-id', is_active: false }))
    const client = new PersonaClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    const created = await client.create(draft)
    expect(created.id).toBe('new-id')
    const url = fetchImpl.mock.calls[0]?.[0]
    const init = fetchImpl.mock.calls[0]?.[1]
    expect(url).toBe('http://127.0.0.1:8000/api/personas')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toMatchObject({ character_name: 'miya' })
  })

  it('activates and deactivates a persona', async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(fullProfile))
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
    const client = new PersonaClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await client.activate('a')
    await client.deactivate()
    expect(fetchImpl.mock.calls[0]?.[0]).toBe('http://127.0.0.1:8000/api/personas/a/activate')
    expect(fetchImpl.mock.calls[1]?.[0]).toBe('http://127.0.0.1:8000/api/personas/deactivate')
  })

  it('rolls back to a selected version', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(fullProfile))
    const client = new PersonaClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await client.rollback('a', 'v1')
    const url = fetchImpl.mock.calls[0]?.[0]
    const init = fetchImpl.mock.calls[0]?.[1]
    expect(url).toBe('http://127.0.0.1:8000/api/personas/a/rollback')
    expect(JSON.parse(String(init?.body))).toEqual({ version_id: 'v1' })
  })

  it('surfaces gateway errors with a local reason', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new Error('offline'))
    const client = new PersonaClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })
    await expect(client.list()).rejects.toEqual(new PersonaClientError('人格网关不可用：offline'))
  })
})
