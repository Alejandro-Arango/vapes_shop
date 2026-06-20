import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';


const baseUrl = (__ENV.BASE_URL || 'http://127.0.0.1:8080').replace(/\/+$/, '');
const pressureRate = Number.parseInt(__ENV.PRESSURE_RATE || '300', 10);
const pressureDuration = __ENV.PRESSURE_DURATION || '15s';
const expectedMinimumRequests = Number.parseInt(
  __ENV.MINIMUM_PRESSURE_REQUESTS || '500',
  10,
);

const pressureAccepted = new Counter('pressure_accepted');
const pressureShed = new Counter('pressure_shed');
const pressureUnexpected = new Counter('pressure_unexpected');

http.setResponseCallback(http.expectedStatuses(200, 429, 502, 503, 504));

export const options = {
  discardResponseBodies: true,
  scenarios: {
    pressure: {
      executor: 'constant-arrival-rate',
      rate: pressureRate,
      timeUnit: '1s',
      duration: pressureDuration,
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    pressure_accepted: ['count>0'],
    pressure_shed: ['count>0'],
    pressure_unexpected: ['count==0'],
    http_reqs: [`count>=${expectedMinimumRequests}`],
  },
};

export default function () {
  const response = http.get(
    `${baseUrl}/api/products/?page=1&page_size=24`,
    {
      redirects: 0,
      tags: { endpoint: 'pressure-catalog' },
      timeout: '5s',
    },
  );

  if (response.status === 200) {
    pressureAccepted.add(1);
    check(response, {
      'respuesta aceptada es JSON': (result) =>
        String(result.headers['Content-Type'] || '').includes(
          'application/json',
        ),
    });
    return;
  }

  if ([0, 429, 502, 503, 504].includes(response.status)) {
    pressureShed.add(1);
    return;
  }

  pressureUnexpected.add(1);
  check(response, {
    'presion no produce estado inesperado': () => false,
  });
}

function metricCount(data, metricName) {
  const metric = data.metrics[metricName];

  if (!metric || !metric.values || metric.values.count === undefined) {
    return 0;
  }

  return metric.values.count;
}

export function handleSummary(data) {
  const summary = {
    accepted: metricCount(data, 'pressure_accepted'),
    requests: metricCount(data, 'http_reqs'),
    shed: metricCount(data, 'pressure_shed'),
    unexpected: metricCount(data, 'pressure_unexpected'),
  };

  return {
    stdout: `Presion controlada: ${JSON.stringify(summary)}\n`,
    'recovery-pressure-summary.json': `${JSON.stringify(data, null, 2)}\n`,
  };
}
