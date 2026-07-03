export async function GET(request: Request) {
  const auth = request.headers.get('Authorization');
  const headers: Record<string, string> = { 'X-Internal': 'true' };
  if (auth) headers['Authorization'] = auth;
  const baseUrl = `${process.env.NEXT_PUBLIC_API_URL?.replace("/api/v1", "") || "http://localhost:8001"}`;
  const response = await fetch(`${baseUrl}/api/v1/analytics/dashboard/live-workshop-status`, { headers });
  const data = await response.json();
  return Response.json(data);
}
