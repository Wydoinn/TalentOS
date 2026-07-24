import '@angular/compiler';
import {describe, expect, it} from 'vitest';

import {routes} from './app.routes';

describe('app routes', () => {
  it('keeps auth login as the explicit unauthenticated entry point', () => {
    const authRoute = routes.find((route) => route.path === 'auth');
    expect(authRoute).toBeTruthy();

    const children = authRoute?.children ?? [];
    expect(children.some((child) => child.path === 'login')).toBe(true);
    expect(children.some((child) => child.path === '' && child.redirectTo === 'login')).toBe(true);
  });

  it('includes the candidate access gateway route', () => {
    const authRoute = routes.find((route) => route.path === 'auth');
    const children = authRoute?.children ?? [];

    expect(children.some((child) => child.path === 'candidate/access')).toBe(true);
  });

  it('allows both manager and candidate users to access the chat route', () => {
    const rootRoute = routes.find((route) => route.path === '');
    const chatRoute = rootRoute?.children?.find((child) => child.path === 'chat');
    const roles = Array.isArray(chatRoute?.data?.['roles']) ? chatRoute?.data?.['roles'] as string[] : [];

    expect(roles).toContain('pm');
    expect(roles).toContain('candidate');
  });
});
