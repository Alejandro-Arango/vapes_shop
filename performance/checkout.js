import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { Counter } from 'k6/metrics';


const fixturePath =
  __ENV.CHECKOUT_FIXTURE_PATH || '/runtime/checkout-fixture.json';
const fixture = JSON.parse(open(fixturePath));
const baseUrl = (__ENV.BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const expectedSuccesses = fixture.available_stock;
const expectedRejections = fixture.buyer_count - fixture.available_stock;

const checkoutSuccesses = new Counter('checkout_successes');
const checkoutRejections = new Counter('checkout_rejections');
const checkoutReplays = new Counter('checkout_replays');
const checkoutUnexpected = new Counter('checkout_unexpected');

http.setResponseCallback(http.expectedStatuses(200, 400));

export const options = {
  scenarios: {
    checkout_contention: {
      executor: 'per-vu-iterations',
      vus: fixture.buyer_count,
      iterations: 1,
      maxDuration: '45s',
      gracefulStop: '5s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate==1'],
    checkout_successes: [`count==${expectedSuccesses}`],
    checkout_rejections: [`count==${expectedRejections}`],
    checkout_replays: [`count==${expectedSuccesses}`],
    checkout_unexpected: ['count==0'],
    'http_req_duration{endpoint:checkout}': ['p(95)<2000', 'p(99)<5000'],
  },
};

function parseJson(response) {
  try {
    return response.json();
  } catch (error) {
    return {};
  }
}

function requestParams(buyer) {
  return {
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': buyer.csrf_token,
      'Idempotency-Key': buyer.idempotency_key,
      Cookie: [
        `${fixture.session_cookie_name}=${buyer.session_key}`,
        `${fixture.csrf_cookie_name}=${buyer.csrf_token}`,
      ].join('; '),
    },
    redirects: 0,
    tags: { endpoint: 'checkout' },
    timeout: '15s',
  };
}

function checkoutPayload(buyerIndex) {
  return JSON.stringify({
    shippingName: `Cliente carga ${buyerIndex + 1}`,
    shippingPhone: '3001234567',
    shippingAddress: `Calle carga ${buyerIndex + 1}`,
    shippingCity: 'Medellin',
    shippingNotes: 'Prueba efimera de concurrencia',
    ageConfirmed: true,
  });
}

export default function () {
  const buyerIndex = exec.vu.idInTest - 1;
  const buyer = fixture.buyers[buyerIndex];

  if (!buyer) {
    checkoutUnexpected.add(1);
    check(null, {
      'cada VU tiene una sesion preparada': () => false,
    });
    return;
  }

  const payload = checkoutPayload(buyerIndex);
  const params = requestParams(buyer);
  const response = http.post(
    `${baseUrl}/api/orders/checkout/`,
    payload,
    params,
  );
  const responseBody = parseJson(response);

  if (response.status === 200) {
    const successValid = check(responseBody, {
      'checkout exitoso crea una orden': (body) =>
        Number.isInteger(body.order_id) && body.order_id > 0,
      'checkout inicial no es replay': (body) =>
        body.idempotent_replay === false,
    });

    if (!successValid) {
      checkoutUnexpected.add(1);
      return;
    }

    checkoutSuccesses.add(1);

    const replay = http.post(
      `${baseUrl}/api/orders/checkout/`,
      payload,
      params,
    );
    const replayBody = parseJson(replay);
    const replayValid = check(replayBody, {
      'reintento idempotente responde 200': () => replay.status === 200,
      'reintento devuelve la misma orden': (body) =>
        body.order_id === responseBody.order_id,
      'reintento se marca como replay': (body) =>
        body.idempotent_replay === true,
    });

    if (replayValid) {
      checkoutReplays.add(1);
    } else {
      checkoutUnexpected.add(1);
    }

    return;
  }

  if (response.status === 400) {
    const rejectionValid = check(responseBody, {
      'rechazo por contencion es controlado': (body) =>
        typeof body.error === 'string' && body.error.length > 0,
    });

    if (rejectionValid) {
      checkoutRejections.add(1);
    } else {
      checkoutUnexpected.add(1);
    }

    return;
  }

  checkoutUnexpected.add(1);
  check(response, {
    'checkout no devuelve estado inesperado': () => false,
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
    buyers: fixture.buyer_count,
    initial_stock: fixture.available_stock,
    successes: metricCount(data, 'checkout_successes'),
    rejections: metricCount(data, 'checkout_rejections'),
    replays: metricCount(data, 'checkout_replays'),
    unexpected: metricCount(data, 'checkout_unexpected'),
  };

  return {
    stdout: `Checkout concurrente: ${JSON.stringify(summary)}\n`,
    'checkout-summary.json': `${JSON.stringify(data, null, 2)}\n`,
  };
}
