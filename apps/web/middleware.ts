import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const MOBILE_USER_AGENT_RE = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini|mobile|windows phone/i;

function isMobileUserAgent(userAgent: string): boolean {
  return MOBILE_USER_AGENT_RE.test(userAgent);
}

function isAllowedOnMobile(pathname: string): boolean {
  if (pathname === "/" || pathname === "/desktop-only") {
    return true;
  }

  if (pathname === "/docs" || pathname.startsWith("/docs/")) {
    return true;
  }

  return false;
}

export function middleware(request: NextRequest) {
  const userAgent = request.headers.get("user-agent") ?? "";

  if (!isMobileUserAgent(userAgent)) {
    return NextResponse.next();
  }

  if (isAllowedOnMobile(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const redirectUrl = request.nextUrl.clone();
  redirectUrl.pathname = "/desktop-only";
  redirectUrl.search = "";

  return NextResponse.redirect(redirectUrl);
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
