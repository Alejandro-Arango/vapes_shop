import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';


const fixturePath =
  __ENV.CANCEL_FIXTURE_PATH || '/runtime/cancel-fixture.json';
const fixture = JSON.parse(open(fixturePath));
const baseUrl = (__ENV.BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const expectedRejections = fixture.request_count - 1;

const cancelSuccesses = new Counter('cancel_successes');
const cancelRejections = new Counter('cancel_rejections');
const cancelUnexpected = new Counter('cancel_unexpected');

http.setResponseCallback(http.expectedStatuses(200, 400));

export const options = {
  scenarios: {
    cancel_contention: {
      executor: 'per-vu-iterations',
      vus: fixture.request_count,
      iterations: 1,
      maxDuration: '45s',
      gracefulStop: '5s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate==1'],
    cancel_successes: ['count==1'],
    cancel_rejections: [`count==${expectedRejections}`],
    cancel_unexpected: ['count==0'],
    'http_req_duration{endpoint:cancel-order}': [
      'p(95)<2000',
      'p(99)<5000',
    ],
  },
};

function parseJson(response) {
  try {
    return response.json();
  } catch (error) {
    return {};
  }
}

function requestParams() {
  return {
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': fixture.csrf_token,
      Cookie: [
        `${fixture.session_cookie_name}=${fixture.session_key}`,
        `${fixture.csrf_cookie_name}=${fixture.csrf_token}`,
      ].join('; '),
    },
    redirects: 0,
    tags: { endpoint: 'cancel-order' },
    timeout: '15s',
  };
}

export default function () {
  const response = http.post(
    `${baseUrl}/api/orders/cancel/${fixture.order_id}/`,
    '{}',
    requestParams(),
  );
  const responseBody = parseJson(response);

  if (response.status === 200) {
    const successValid = check(responseBody, {
      'una cancelacion confirma la orden': (body) =>
        typeof body.message === 'string' &&
        body.message.includes(`#${fixture.order_id}`),
    });

    if (successValid) {
      cancelSuccesses.add(1);
    } else {
      cancelUnexpected.add(1);
    }

    return;
  }

  if (response.status === 400) {
    const rejectionValid = check(responseBody, {
      'cancelacion repetida se rechaza como cerrada': (body) =>
        typeof body.error === 'string' &&
        body.error.toLowerCase().includes('cerrada'),
    });

    if (rejectionValid) {
      cancelRejections.add(1);
    } else {
      cancelUnexpected.add(1);
    }

    return;
  }

  cancelUnexpected.add(1);
  check(response, {
    'cancelacion no devuelve estado inesperado': () => false,
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
    requests: fixture.request_count,
    successes: metricCount(data, 'cancel_successes'),
    rejections: metricCount(data, 'cancel_rejections'),
    unexpected: metricCount(data, 'cancel_unexpected'),
  };

  return {
    stdout: `Cancelacion concurrente: ${JSON.stringify(summary)}\n`,
    'cancel-summary.json': `${JSON.stringify(data, null, 2)}\n`,
  };
}
