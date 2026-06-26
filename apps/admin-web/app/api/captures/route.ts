export async function POST(request: Request) {
  const formData = await request.formData();
  const token = formData.get('token') as string;
  const stage_id = formData.get('stage_id') as string;
  const image = formData.get('image');
  
  const fd = new FormData();
  if (image) fd.append('image', image as Blob);
  
  const response = await fetch(
    `http://76.13.223.20:8001/api/v1/captures/?stage_id=${stage_id}`,
    { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: fd }
  );
  const data = await response.json();
  return Response.json(data);
}
