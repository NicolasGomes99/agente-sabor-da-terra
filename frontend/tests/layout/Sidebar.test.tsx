import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { Sidebar } from '../../src/components/layout/Sidebar'
import { AuthContext } from '../../src/features/auth/auth-context'

function LocationProbe() {
  return <span data-testid="location">{useLocation().pathname}</span>
}

describe('Sidebar', () => {
  it('logs out and navigates to login', () => {
    const logout = vi.fn()

    render(
      <AuthContext.Provider
        value={{
          accessToken: 'access-token',
          isAuthenticated: true,
          login: vi.fn(),
          logout,
        }}
      >
        <MemoryRouter initialEntries={['/chat']}>
          <Sidebar />
          <LocationProbe />
        </MemoryRouter>
      </AuthContext.Provider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Sair' }))

    expect(logout).toHaveBeenCalledOnce()
    expect(screen.getByTestId('location').textContent).toBe('/login')
  })
})
