/**
 * NEXORA UCMP — CLIENT-SIDE HASH ROUTER
 * Public website (Landing page) is the default and only view before sign in.
 * Authenticated console routes (overview, jobs, etc.) require active session.
 */

import { isAuthenticated } from './auth.js';
import { renderLandingPage, initLandingEvents } from './pages/landing.js';
import { renderOverviewPage, initOverviewEvents } from './pages/overview.js';
import { renderJobsPage, initJobsEvents } from './pages/jobs.js';
import { renderProvidersPage, initProvidersEvents } from './pages/providers.js';
import { renderResourcePoolPage, initResourcePoolEvents } from './pages/resource-pool.js';
import { renderBillingPage, initBillingEvents } from './pages/billing.js';
import { renderAnalyticsPage, initAnalyticsEvents } from './pages/analytics.js';
import { renderSettingsPage, initSettingsEvents } from './pages/settings.js';
import { renderStreamingPage, initStreamingEvents } from './pages/streaming.js';
import { renderSidebar, initSidebarEvents } from './components/sidebar.js';
import { renderTopbar, initTopbarEvents } from './components/topbar.js';

const routes = {
  'home': { render: renderLandingPage, init: initLandingEvents, isLanding: true },
  'landing': { render: renderLandingPage, init: initLandingEvents, isLanding: true },
  'overview': { render: renderOverviewPage, init: initOverviewEvents, isLanding: false },
  'jobs': { render: renderJobsPage, init: initJobsEvents, isLanding: false },
  'streaming': { render: renderStreamingPage, init: initStreamingEvents, isLanding: false },
  'providers': { render: renderProvidersPage, init: initProvidersEvents, isLanding: false },
  'resource-pool': { render: renderResourcePoolPage, init: initResourcePoolEvents, isLanding: false },
  'billing': { render: renderBillingPage, init: initBillingEvents, isLanding: false },
  'analytics': { render: renderAnalyticsPage, init: initAnalyticsEvents, isLanding: false },
  'settings': { render: renderSettingsPage, init: initSettingsEvents, isLanding: false },
};

let currentRouteId = 'home';

export function getCurrentRoute() {
  return currentRouteId;
}

export function navigateTo(routeId) {
  window.location.hash = `#/${routeId}`;
}

export function handleRoute() {
  const hash = window.location.hash.replace(/^#\/?/, '').trim();
  const cleanRoute = hash.split('?')[0].split('/')[0].toLowerCase();
  
  // Default to public home/landing page if empty or invalid route
  if (!cleanRoute || cleanRoute === '' || cleanRoute === 'home' || cleanRoute === 'landing') {
    currentRouteId = 'home';
  } else {
    currentRouteId = routes[cleanRoute] ? cleanRoute : 'home';
  }

  // STRICT RULE: Public website (landing page) MUST be the page before sign in!
  // Any console route accessed without an active session redirects to the public landing page.
  if (!isAuthenticated() && !routes[currentRouteId]?.isLanding) {
    currentRouteId = 'home';
    if (window.location.hash !== '#/home') {
      window.location.hash = '#/home';
      return; // hashchange will invoke handleRoute cleanly
    }
  }

  const routeObj = routes[currentRouteId];
  const appRoot = document.getElementById('app-root');

  // Toggle landing-mode layout class
  if (appRoot) {
    if (routeObj.isLanding) {
      appRoot.classList.add('landing-mode');
    } else {
      appRoot.classList.remove('landing-mode');
    }
  }

  // 1. Re-render Shell parts only for Console views
  if (!routeObj.isLanding) {
    const sidebarContainer = document.getElementById('sidebar-container');
    if (sidebarContainer) {
      sidebarContainer.innerHTML = renderSidebar(currentRouteId);
      initSidebarEvents();
    }

    const topbarContainer = document.getElementById('topbar-container');
    if (topbarContainer) {
      topbarContainer.innerHTML = renderTopbar(currentRouteId);
      initTopbarEvents();
    }
  } else {
    // In landing mode, clear out console shell containers completely
    const sidebarContainer = document.getElementById('sidebar-container');
    if (sidebarContainer) sidebarContainer.innerHTML = '';

    const topbarContainer = document.getElementById('topbar-container');
    if (topbarContainer) topbarContainer.innerHTML = '';
  }

  // 2. Render Page Content
  const contentContainer = document.getElementById('page-content');
  if (contentContainer) {
    contentContainer.innerHTML = routeObj.render();
    if (routeObj.init) {
      try {
        routeObj.init();
      } catch (err) {
        console.error(`Route init error for ${currentRouteId}:`, err);
      }
    }
  }

  // Scroll to top
  window.scrollTo({ top: 0, behavior: 'instant' });
}

export function initRouter() {
  window.addEventListener('hashchange', handleRoute);
  
  // Custom event for reactive re-render without hash change
  window.addEventListener('nexora:rerender', () => {
    handleRoute();
  });

  // Initial trigger
  handleRoute();
}
