export async function POST(request: Request) {
  const body = await request.formData();
  const response = await fetch('http://localhost:8001/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      username: body.get('username') as string,
      password: body.get('password') as string,
    }),
  });
  const data = await response.json();
  return Response.json(data);
}
