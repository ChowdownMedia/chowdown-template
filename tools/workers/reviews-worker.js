/**
 * Chowdown Reviews Worker
 * Cloudflare Worker that proxies Google Places API reviews.
 *
 * Endpoint: GET /api/reviews?placeId=XXXXX
 * Returns:  { reviews: [{ author, rating, text, time }] }
 *
 * Environment variables (set in Cloudflare dashboard, never in code):
 *   GOOGLE_PLACES_API_KEY — Google Places API key
 *
 * Behavior:
 *   - Fetches reviews from Google Places API (New) for the given placeId
 *   - Filters to 4+ star reviews
 *   - Returns up to 5 reviews sorted by most recent
 *   - Caches responses for 15 minutes (900s) via Cache API
 *   - Returns empty array on any error — client handles fallback
 *   - CORS headers allow any origin (static sites on different domains)
 *
 * Deploy:
 *   wrangler deploy tools/workers/reviews-worker.js --name chowdown-reviews
 *
 * One Worker serves ALL Chowdown clients — placeId differentiates them.
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    // Only handle /api/reviews
    if (url.pathname !== '/api/reviews') {
      return new Response('Not found', { status: 404, headers: corsHeaders() });
    }

    const placeId = url.searchParams.get('placeId');
    if (!placeId) {
      return jsonResponse({ error: 'placeId parameter required', reviews: [] }, 400);
    }

    // Check cache first
    const cacheKey = new Request(url.toString(), request);
    const cache = caches.default;
    let cached = await cache.match(cacheKey);
    if (cached) {
      return cached;
    }

    try {
      const reviews = await fetchGoogleReviews(placeId, env.GOOGLE_PLACES_API_KEY);
      const filtered = reviews
        .filter(r => r.rating >= 4)
        .sort((a, b) => b.time - a.time)
        .slice(0, 5);

      const response = jsonResponse({ reviews: filtered }, 200);

      // Cache for 15 minutes
      response.headers.set('Cache-Control', 'public, max-age=900');
      await cache.put(cacheKey, response.clone());

      return response;
    } catch (err) {
      // Any error: return empty reviews — client-side handles fallback
      return jsonResponse({ reviews: [], error: 'Failed to fetch reviews' }, 200);
    }
  }
};

/**
 * Fetch reviews from Google Places API (New).
 * Uses the Places API v1 endpoint.
 */
async function fetchGoogleReviews(placeId, apiKey) {
  if (!apiKey) {
    throw new Error('GOOGLE_PLACES_API_KEY not configured');
  }

  // Google Places API (New) — get place details with reviews
  const apiUrl = `https://places.googleapis.com/v1/places/${placeId}`;

  const response = await fetch(apiUrl, {
    method: 'GET',
    headers: {
      'X-Goog-Api-Key': apiKey,
      'X-Goog-FieldMask': 'reviews'
    }
  });

  if (!response.ok) {
    throw new Error(`Google API returned ${response.status}`);
  }

  const data = await response.json();

  if (!data.reviews || !Array.isArray(data.reviews)) {
    return [];
  }

  return data.reviews.map(r => ({
    author: r.authorAttribution?.displayName || 'Anonymous',
    rating: r.rating || 0,
    text: r.text?.text || '',
    time: r.publishTime ? new Date(r.publishTime).getTime() / 1000 : 0
  }));
}

/**
 * JSON response with CORS headers.
 */
function jsonResponse(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...corsHeaders()
    }
  });
}

/**
 * CORS headers — allow any origin since client sites are on different domains.
 * API key is server-side only (env var) — never exposed to browser.
 */
function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
  };
}
