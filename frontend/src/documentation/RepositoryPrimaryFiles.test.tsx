import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'
import { NavigationGuardProvider } from '../navigation/NavigationGuardProvider'
import type { DocumentPrimaryFile } from './api'
import { RepositoryPrimaryFiles } from './RepositoryPrimaryFiles'
import { browserRepositoryClient, RepositoryPrimaryFileConflictError, type RepositoryClient } from './repositoryApi'

function version(number: number, current = true): DocumentPrimaryFile {
  return {
    id: '11111111-1111-4111-8111-' + String(number).padStart(12, '0'),
    filename: 'source-v' + number + '.txt', media_type: 'text/plain', size: 5,
    checksum: 'a'.repeat(64), scan_status: 'clean', scan_engine: 'synthetic',
    scanned_at: '2026-11-03T12:00:00Z', created_at: '2026-11-03T12:00:00Z',
    version_number: number, replaces_id: number === 1 ? null : '11111111-1111-4111-8111-' + String(number - 1).padStart(12, '0'),
    is_current: current,
  }
}
const history = (results: DocumentPrimaryFile[], count = results.length, page = 1) => ({ results, count, page, page_size: 25, has_more: page * 25 < count })

function setup(overrides: Partial<RepositoryClient> = {}, canWrite = true) {
  const client = {
    ...browserRepositoryClient,
    primaryFiles: vi.fn().mockResolvedValue(history([])),
    appendPrimaryFile: vi.fn(),
    ...overrides,
  }
  const onEditingChange = vi.fn()
  const router = createMemoryRouter([{ path: '*', element: <NavigationGuardProvider>
    <RepositoryPrimaryFiles contentId="doc-1" organizationId="org-1" client={client} canWrite={canWrite} onEditingChange={onEditingChange} />
  </NavigationGuardProvider> }])
  const view = render(<RouterProvider router={router} />)
  return { client, onEditingChange, ...view }
}

it('loads history only on request and appends the first scanned file explicitly', async () => {
  const user = userEvent.setup()
  const primaryFiles = vi.fn().mockResolvedValueOnce(history([])).mockResolvedValue(history([version(1)]))
  const appendPrimaryFile = vi.fn().mockResolvedValue(version(1))
  setup({ primaryFiles, appendPrimaryFile })
  expect(primaryFiles).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
  expect(await screen.findByText('No primary file yet.')).toBeVisible()
  const file = new File(['first'], 'first.txt', { type: 'text/plain' })
  await user.upload(screen.getByLabelText('Choose primary file'), file)
  expect(appendPrimaryFile).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Upload primary file' }))
  expect(await screen.findByRole('button', { name: 'Download source-v1.txt, version 1' })).toBeEnabled()
  expect(appendPrimaryFile).toHaveBeenCalledWith('doc-1', file, null, 'org-1', expect.any(AbortSignal))
  expect(screen.queryByText('Selected: first.txt')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Refresh file versions' })).toBeEnabled()
})

it('requires explicit replacement confirmation and retains the earlier download', async () => {
  const user = userEvent.setup()
  const primaryFiles = vi.fn().mockResolvedValueOnce(history([version(1)])).mockResolvedValue(history([version(2), version(1, false)]))
  const appendPrimaryFile = vi.fn().mockResolvedValue(version(2))
  setup({ primaryFiles, appendPrimaryFile })
  await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
  await screen.findByRole('button', { name: 'Download source-v1.txt, version 1' })
  const file = new File(['second'], 'second.txt')
  await user.upload(screen.getByLabelText('Choose primary file'), file)
  expect(screen.getByRole('button', { name: 'Replace primary file' })).toBeDisabled()
  await user.click(screen.getByLabelText('Replace version 1; keep all earlier versions'))
  await user.click(screen.getByRole('button', { name: 'Replace primary file' }))
  await screen.findByRole('button', { name: 'Download source-v2.txt, version 2' })
  expect(screen.getByRole('button', { name: 'Download source-v1.txt, version 1' })).toBeVisible()
  expect(appendPrimaryFile).toHaveBeenCalledWith('doc-1', file, version(1).id, 'org-1', expect.any(AbortSignal))
})

it.each([new RepositoryPrimaryFileConflictError(), new Error('Denied')])('keeps a failed selection and requires refreshed target confirmation', async failure => {
  const user = userEvent.setup()
  const primaryFiles = vi.fn().mockResolvedValueOnce(history([version(1)])).mockResolvedValueOnce(history([version(2), version(1, false)])).mockResolvedValue(history([version(3), version(2, false), version(1, false)]))
  const appendPrimaryFile = vi.fn().mockRejectedValueOnce(failure).mockResolvedValue(version(3))
  setup({ primaryFiles, appendPrimaryFile })
  await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
  await screen.findByRole('button', { name: 'Download source-v1.txt, version 1' })
  const file = new File(['replacement'], 'replacement.txt')
  await user.upload(screen.getByLabelText('Choose primary file'), file)
  await user.click(screen.getByLabelText('Replace version 1; keep all earlier versions'))
  await user.click(screen.getByRole('button', { name: 'Replace primary file' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Your selected file is kept here')
  expect(screen.getByText('Selected: replacement.txt')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Replace primary file' })).toBeDisabled()
  expect(appendPrimaryFile).toHaveBeenCalledTimes(1)
  await user.click(screen.getByRole('button', { name: 'Refresh file versions' }))
  const confirmation = await screen.findByLabelText('Replace version 2; keep all earlier versions')
  expect(confirmation).not.toBeChecked()
  expect(screen.getByRole('button', { name: 'Replace primary file' })).toBeDisabled()
  await user.click(confirmation)
  await user.click(screen.getByRole('button', { name: 'Replace primary file' }))
  await waitFor(() => expect(appendPrimaryFile).toHaveBeenCalledTimes(2))
  expect(appendPrimaryFile).toHaveBeenLastCalledWith('doc-1', file, version(2).id, 'org-1', expect.any(AbortSignal))
})

it('clears replacement confirmation on refresh without discarding the selected file', async () => {
  const user = userEvent.setup()
  const primaryFiles = vi.fn().mockResolvedValueOnce(history([version(1)])).mockResolvedValue(history([version(2), version(1, false)]))
  const { client } = setup({ primaryFiles })
  await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
  await screen.findByRole('button', { name: 'Download source-v1.txt, version 1' })
  await user.upload(screen.getByLabelText('Choose primary file'), new File(['chosen'], 'chosen.txt'))
  await user.click(screen.getByLabelText('Replace version 1; keep all earlier versions'))
  await user.click(screen.getByRole('button', { name: 'Refresh file versions' }))
  expect(await screen.findByLabelText('Replace version 2; keep all earlier versions')).not.toBeChecked()
  expect(screen.getByText('Selected: chosen.txt')).toBeVisible()
  expect(client.appendPrimaryFile).not.toHaveBeenCalled()
})

it('keeps read denial retryable and leaves stale source upload disabled', async () => {
  const user = userEvent.setup()
  const primaryFiles = vi.fn().mockRejectedValueOnce(new Error('Denied')).mockResolvedValue(history([]))
  const { client } = setup({ primaryFiles }, false)
  await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('File versions could not be loaded')
  expect(screen.getByLabelText('Choose primary file')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Refresh file versions' }))
  await screen.findByText('No primary file yet.')
  expect(screen.getByLabelText('Choose primary file')).toBeDisabled()
  expect(client.appendPrimaryFile).not.toHaveBeenCalled()
})

it('pages retained versions without replacing the current page or its downloads', async () => {
  const user = userEvent.setup()
  const primaryFiles = vi.fn().mockResolvedValueOnce(history(Array.from({ length: 25 }, (_, i) => version(26 - i, i === 0)), 26)).mockResolvedValue(history([version(1, false)], 26, 2))
  setup({ primaryFiles })
  await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
  await user.click(await screen.findByRole('button', { name: 'More file versions' }))
  await screen.findByRole('button', { name: 'Download source-v1.txt, version 1' })
  expect(screen.getAllByRole('button', { name: /^Download source-/ })).toHaveLength(26)
  expect(primaryFiles).toHaveBeenLastCalledWith('doc-1', 'org-1', 2, expect.any(AbortSignal))
})

it('does not acknowledge a mutation with mismatched lineage or release its selected file', async () => {
  const user = userEvent.setup()
  setup({ appendPrimaryFile: vi.fn().mockResolvedValue(version(2)) })
  await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
  await screen.findByText('No primary file yet.')
  await user.upload(screen.getByLabelText('Choose primary file'), new File(['first'], 'first.txt'))
  await user.click(screen.getByRole('button', { name: 'Upload primary file' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The upload could not be confirmed')
  expect(screen.getByText('Selected: first.txt')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Upload primary file' })).toBeDisabled()
})

it('refuses to append pages when concurrent replacement changes the version count', async () => {
  const user = userEvent.setup()
  const primaryFiles = vi.fn().mockResolvedValueOnce(history(Array.from({ length: 25 }, (_, i) => version(26 - i, i === 0)), 26))
    .mockResolvedValueOnce(history([version(2, false), version(1, false)], 27, 2))
    .mockResolvedValue(history(Array.from({ length: 25 }, (_, i) => version(27 - i, i === 0)), 27))
  const { client } = setup({ primaryFiles })
  await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
  await user.click(await screen.findByRole('button', { name: 'More file versions' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('File versions changed while loading')
  expect(screen.queryAllByRole('button', { name: /^Download source-/ })).toHaveLength(0)
  expect(screen.getByLabelText('Choose primary file')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: 'Refresh file versions' }))
  await screen.findByRole('button', { name: 'Download source-v27.txt, version 27' })
  expect(primaryFiles).toHaveBeenLastCalledWith('doc-1', 'org-1', 1, expect.any(AbortSignal))
  expect(client.appendPrimaryFile).not.toHaveBeenCalled()
})

it('aborts an unfinished history request when the document is closed', async () => {
  let finish!: (value: ReturnType<typeof history>) => void
  const pending = new Promise<ReturnType<typeof history>>(resolve => { finish = resolve })
  const primaryFiles = vi.fn().mockReturnValue(pending)
  const { unmount } = setup({ primaryFiles })
  await userEvent.setup().click(screen.getByRole('button', { name: 'Primary file versions' }))
  const signal = primaryFiles.mock.calls[0][3] as AbortSignal
  unmount()
  expect(signal.aborted).toBe(true)
  await act(async () => { finish(history([version(1)])); await pending })
})

it('keeps a denied download retryable without navigating or losing a file selection', async () => {
  const user = userEvent.setup()
  const downloadPrimaryFile = vi.fn().mockRejectedValueOnce(new Error('Denied')).mockResolvedValue({ content: new Blob(['first']), name: 'source-v1.txt' })
  const create = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
  const revoke = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  const createObjectURL = vi.fn().mockReturnValue('blob:primary-file')
  const revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL })
  try {
    setup({ primaryFiles: vi.fn().mockResolvedValue(history([version(1)])), downloadPrimaryFile })
    await user.click(screen.getByRole('button', { name: 'Primary file versions' }))
    const download = await screen.findByRole('button', { name: 'Download source-v1.txt, version 1' })
    await user.upload(screen.getByLabelText('Choose primary file'), new File(['chosen'], 'chosen.txt'))
    await user.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('The file could not be downloaded')
    expect(screen.getByText('Selected: chosen.txt')).toBeVisible()
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(click).not.toHaveBeenCalled()
    await user.click(download)
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:primary-file'))
    expect(click).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Selected: chosen.txt')).toBeVisible()
    expect(downloadPrimaryFile).toHaveBeenLastCalledWith('doc-1', version(1), 'org-1', expect.any(AbortSignal))
  } finally {
    click.mockRestore()
    if (create) Object.defineProperty(URL, 'createObjectURL', create)
    else Reflect.deleteProperty(URL, 'createObjectURL')
    if (revoke) Object.defineProperty(URL, 'revokeObjectURL', revoke)
    else Reflect.deleteProperty(URL, 'revokeObjectURL')
  }
})
