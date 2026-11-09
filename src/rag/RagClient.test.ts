import { describe, expect, it, vi } from 'vitest'
import { RagClient, RagClientError } from './RagClient'

describe('RagClient', () => {
  it('searches a selected collection through the local gateway', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({
        collection: 'character_knowledge',
        results: [{
          document_id: 'doc-1',
          filename: 'character.md',
          source_label: 'character sheet',
          chunk_index: 0,
          content: 'The pet likes moon tea.',
          updated_at: 1,
          score: 0.9,
        }],
      }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const client = new RagClient({ baseUrl: 'http://127.0.0.1:8000/', fetchImpl })

    await expect(client.search({
      collection: 'character_knowledge',
      query: '  What does the pet like? ',
    })).resolves.toMatchObject({ collection: 'character_knowledge' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/rag/search',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          collection: 'character_knowledge',
          query: 'What does the pet like?',
          limit: 5,
        }),
      }),
    )
    expect(fetchImpl.mock.contexts[0]).toBe(globalThis)
  })

  it('uploads documents using multipart form data', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify({
        collection: 'user_documents',
        document_id: 'doc-2',
        filename: 'notes.md',
        source_label: 'notes',
        chunk_count: 1,
        updated_at: 2,
      }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const client = new RagClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })
    const document = new File(['# Notes'], 'notes.md', { type: 'text/markdown' })

    await expect(client.ingest({
      collection: 'user_documents',
      document,
      sourceLabel: ' notes ',
    })).resolves.toMatchObject({ document_id: 'doc-2' })
    expect(fetchImpl).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/rag/documents',
      expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData),
      }),
    )
  })

  it('surfaces gateway errors with a local failure reason', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockRejectedValue(new Error('offline'))
    const client = new RagClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    await expect(client.health()).rejects.toEqual(new RagClientError('知识库网关不可用：offline'))
  })

  it('lists uploaded documents in a collection', async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(
      JSON.stringify([{
        collection: 'character_knowledge',
        document_id: 'doc-9',
        filename: 'a.md',
        source_label: 'a.md',
        chunk_count: 2,
        updated_at: 3,
        content_hash: 'h',
      }]),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ))
    const client = new RagClient({ baseUrl: 'http://127.0.0.1:8000', fetchImpl })

    const documents = await client.listDocuments('character_knowledge')
    expect(documents).toHaveLength(1)
    expect(documents[0].content_hash).toBe('h')
    expect(fetchImpl.mock.calls[0]?.[0])
      .toBe('http://127.0.0.1:8000/api/rag/documents/character_knowledge')
  })
})
