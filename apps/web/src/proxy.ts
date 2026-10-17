import { NextResponse, type NextRequest } from "next/server";

import { webAccessRejection } from "@/lib/server-access";

export function proxy(request: NextRequest) {
  return webAccessRejection(request) ?? NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
