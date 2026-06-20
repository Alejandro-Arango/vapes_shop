import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { Counter } from 'k6/metrics';


const fixturePath =
  __ENV.COUPON_FIXTURE_PATH || '/runtime/coupon-fixture.json';
const fixture = JSON.parse(open(fixturePath));
const baseUrl = (__ENV.BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const expectedSuccesses = fixture.coupon_max_uses;
const expectedRejections = fixture.buyer_count - fixture.coupon_max_uses;

const couponSuccesses = new Counter('coupon_successes');
const couponRejections = new Counter('coupon_rejections');
const couponReplays = new Counter('coupon_replays');
const couponUnexpected = new Counter('coupon_unexpected');

http.setResponseCallback(http.expectedStatuses(200, 400));

export const options = {
  scenarios: {
    coupon_contention: {
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
    coupon_successes: [`count==${expectedSuccesses}`],
    coupon_rejections: [`count==${expectedRejections}`],
    coupon_replays: [`count==${expectedSuccesses}`],
    coupon_unexpected: ['count==0'],
    'http_req_duration{endpoint:coupon-checkout}': [
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
    tags: { endpoint: 'coupon-checkout' },
    timeout: '15s',
  };
}

function checkoutPayload(buyerIndex) {
  return JSON.stringify({
    shippingName: `Cliente cupon ${buyerIndex + 1}`,
    shippingPhone: '3001234567',
    shippingAddress: `Calle cupon ${buyerIndex + 1}`,
    shippingCity: 'Medellin',
    shippingNotes: 'Prueba efimera de limite de cupon',
    ageConfirmed: true,
  });
}

export default function () {
  const buyerIndex = exec.vu.idInTest - 1;
  const buyer = fixture.buyers[buyerIndex];

  if (!buyer) {
    couponUnexpected.add(1);
    check(null, {
      'cada VU tiene una sesion de cupon': () => false,
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
      'checkout con cupon crea una orden': (body) =>
        Number.isInteger(body.order_id) && body.order_id > 0,
      'orden conserva el codigo del cupon': (body) =>
        body.coupon_code === fixture.coupon_code,
      'checkout inicial de cupon no es replay': (body) =>
        body.idempotent_replay === false,
    });

    if (!successValid) {
      couponUnexpected.add(1);
      return;
    }

    couponSuccesses.add(1);

    const replay = http.post(
      `${baseUrl}/api/orders/checkout/`,
      payload,
      params,
    );
    const replayBody = parseJson(replay);
    const replayValid = check(replayBody, {
      'replay de cupon responde 200': () => replay.status === 200,
      'replay de cupon devuelve la misma orden': (body) =>
        body.order_id === responseBody.order_id,
      'replay de cupon se marca correctamente': (body) =>
        body.idempotent_replay === true,
    });

    if (replayValid) {
      couponReplays.add(1);
    } else {
      couponUnexpected.add(1);
    }

    return;
  }

  if (response.status === 400) {
    const rejectionValid = check(responseBody, {
      'limite de cupon produce rechazo controlado': (body) =>
        body.coupon_invalid === true &&
        typeof body.error === 'string' &&
        body.error.toLowerCase().includes('cupon'),
    });

    if (rejectionValid) {
      couponRejections.add(1);
    } else {
      couponUnexpected.add(1);
    }

    return;
  }

  couponUnexpected.add(1);
  check(response, {
    'cupon no devuelve estado inesperado': () => false,
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
    max_uses: fixture.coupon_max_uses,
    successes: metricCount(data, 'coupon_successes'),
    rejections: metricCount(data, 'coupon_rejections'),
    replays: metricCount(data, 'coupon_replays'),
    unexpected: metricCount(data, 'coupon_unexpected'),
  };

  return {
    stdout: `Cupon concurrente: ${JSON.stringify(summary)}\n`,
    'coupon-summary.json': `${JSON.stringify(data, null, 2)}\n`,
  };
}
