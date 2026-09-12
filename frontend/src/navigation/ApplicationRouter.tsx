import { createContext, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter, createMemoryRouter, RouterProvider } from 'react-router'
import { NavigationGuardProvider } from './NavigationGuardProvider'

const ApplicationContent = createContext<ReactNode>(null)
function Root() {
  return <NavigationGuardProvider>{useContext(ApplicationContent)}</NavigationGuardProvider>
}

export function ApplicationRouter({ children, initialPath }: { children: ReactNode; initialPath?: string }) {
  const [router, setRouter] = useState<ReturnType<typeof createBrowserRouter> | null>(null)
  useEffect(() => {
    // Create/dispose in the effect so StrictMode cannot leak a history listener.
    const routes = [{ path: '*', element: <Root /> }]
    const next = initialPath ? createMemoryRouter(routes, { initialEntries: [initialPath] }) : createBrowserRouter(routes)
    // Router creation attaches external history listeners; this effect owns their cleanup.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRouter(next)
    return () => next.dispose()
  }, [initialPath])
  return <ApplicationContent.Provider value={children}>{router && <RouterProvider router={router} />}</ApplicationContent.Provider>
}
