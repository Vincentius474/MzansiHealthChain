"use client";
import type { Signer } from "ethers";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { short } from "./format";
import { getSession, Session } from "./session";
import { connect } from "./wallet";

/** Guards a page: needs a signed-in session with an allowed role and the matching wallet account. */
export function useSession(allowed: Session["role"][]) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [signer, setSigner] = useState<Signer | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const s = getSession();
    if (!s || !allowed.includes(s.role)) {
      router.replace("/");
      return;
    }
    setSession(s);
    if (!s.address) {
      return;
    }
    const linkedAddress = s.address;
    connect()
      .then((sg) => {
        if (sg.address.toLowerCase() !== linkedAddress.toLowerCase())
          setError(`Your wallet switched accounts. Sign out and sign in again with ${short(linkedAddress)}.`);
        else setSigner(sg);
      })
      .catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { session, signer, error };
}
