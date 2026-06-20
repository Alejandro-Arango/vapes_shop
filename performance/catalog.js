import http from 'k6/http';
import { check, sleep } from 'k6';


const baseUrl = (__ENV.BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const profileName = (__ENV.LOAD_PROFILE || 'smoke').toLowerCase();
const profiles = {
  smoke: {
    executor: 'constant-vus',
    vus: 2,
    duration: '20s',
    gracefulStop: '5s',
  },
  baseline: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: '20s', target: 10 },
      { duration: '40s', target: 10 },
      { duration: '20s', target: 0 },
    ],
    gracefulRampDown: '10s',
  },
};

if (!profiles[profileName]) {
  throw new Error(`LOAD_PROFILE invalido: ${profileName}`);
}

export const options = {
  scenarios: {
    catalog: profiles[profileName],
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
    'http_req_duration{endpoint:catalog}': ['p(95)<750', 'p(99)<1500'],
    'http_req_duration{endpoint:home}': ['p(95)<1000', 'p(99)<2000'],
    'http_req_duration{endpoint:health}': ['p(95)<300'],
  },
};

function request(method, path, endpoint) {
  return {
    method,
    url: `${baseUrl}${path}`,
    params: {
      tags: { endpoint },
      timeout: '10s',
    },
  };
}

export default function () {
  const responses = http.batch([
    request('GET', '/', 'home'),
    request('GET', '/api/categories/', 'catalog'),
    request('GET', '/api/products/?page=1&page_size=24', 'catalog'),
  ]);

  check(responses[0], {
    'home responde 200': (response) => response.status === 200,
  });
  check(responses[1], {
    'categorias responde 200': (response) => response.status === 200,
  });
  check(responses[2], {
    'productos responde 200': (response) => response.status === 200,
    'productos devuelve JSON': (response) =>
      String(response.headers['Content-Type'] || '').includes('application/json'),
  });

  if (__ITER % 10 === 0) {
    const healthResponses = http.batch([
      request('GET', '/api/live/', 'health'),
      request('GET', '/api/health/', 'health'),
    ]);

    check(healthResponses[0], {
      'liveness responde 200': (response) => response.status === 200,
    });
    check(healthResponses[1], {
      'readiness responde 200': (response) => response.status === 200,
    });
  }

  sleep(1);
}

function metricValue(data, metricName, valueName) {
  const metric = data.metrics[metricName];

  if (!metric || !metric.values || metric.values[valueName] === undefined) {
    return 'n/a';
  }

  return metric.values[valueName];
}

export function handleSummary(data) {
  const failedRate = metricValue(data, 'http_req_failed', 'rate');
  const p95 = metricValue(data, 'http_req_duration', 'p(95)');

  return {
    stdout: `Perfil ${profileName}: error=${failedRate}, p95=${p95}ms\n`,
    'performance-summary.json': `${JSON.stringify(data, null, 2)}\n`,
  };
}
