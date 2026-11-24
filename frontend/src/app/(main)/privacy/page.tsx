import type { Metadata } from "next";
import Link from "next/link";
import { TopBar } from "@/components/layout/TopBar";

export const metadata: Metadata = {
  title: "Privacy Policy · Turnup",
  description: "What Turnup collects, why, who we share it with, and your rights under the Nigeria Data Protection Act 2023.",
};

const UPDATED = "24 November 2026";
// Set NEXT_PUBLIC_PRIVACY_EMAIL to the address that handles data requests.
const CONTACT = process.env.NEXT_PUBLIC_PRIVACY_EMAIL || "privacy@turnup.ng";

function H({ id, children }: { id: string; children: React.ReactNode }) {
  return <h2 id={id} className="text-base font-black text-text pt-4 scroll-mt-20">{children}</h2>;
}

export default function PrivacyPage() {
  return (
    <div className="flex flex-col pb-10">
      <TopBar title="Privacy Policy" back />
      <article className="px-4 pt-4 max-w-2xl w-full mx-auto space-y-3 text-sm text-text-secondary leading-relaxed [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1 [&_strong]:text-text">
        <p className="text-xs text-text-muted">Last updated {UPDATED}</p>
        <p>
          Turnup helps you find events, buy tickets and run events and venues. This policy explains what personal
          data we collect, why, who we share it with and the rights you have under the Nigeria Data Protection
          Act 2023 (NDPA). It covers the Turnup website and the Android app.
        </p>

        <H id="collect">What we collect</H>
        <ul>
          <li><strong>Your account:</strong>{" "}name, username, email address and/or phone number, password (stored
            only as a secure hash), profile photo, bio, city and website, and whether you use two-factor sign-in.</li>
          <li><strong>Your preferences:</strong>{" "}the kinds of events you like, your price range, in-person or
            online, and when you usually go out, if you tell us during onboarding or later.</li>
          <li><strong>What you do on Turnup:</strong>{" "}events you save, RSVP to, buy tickets for, check in to,
            review, comment on, share or hide; people, venues and communities you follow or join; searches you ask us
            to watch; and views of event pages, counted for organizers&apos; statistics.</li>
          <li><strong>Payments:</strong>{" "}your orders and ticket codes. Card and bank details go straight to
            Paystack; we never see or store them.</li>
          <li><strong>Devices and sign-in:</strong>{" "}for each signed-in session, the IP address, browser or device
            type and when it was used, so you can see and end sessions in Settings and so we can spot misuse.</li>
          <li><strong>Organizers and venues:</strong>{" "}business details, payout account details (held by Paystack)
            and, for venue verification, identity and ownership documents. Those documents are stored privately,
            viewed only by the admin or agent checking them (every view is logged), and deleted on a fixed
            schedule once verification is complete.</li>
        </ul>

        <H id="why">Why we use it</H>
        <ul>
          <li><strong>To provide Turnup</strong>{" "}(performing our contract with you): your account, tickets and
            check-in, sending your tickets and receipts, organizer and venue tools, Turnup+ memberships.</li>
          <li><strong>To recommend events</strong>{" "}(our legitimate interest in a useful feed): your preferences and
            activity on Turnup shape &quot;For You&quot;, weekend picks and search results. You can hide events or
            organizers at any time, and change your preferences in your profile.</li>
          <li><strong>To keep Turnup safe</strong>{" "}(legitimate interest and legal obligation): preventing fraud,
            chargebacks and account takeovers, and enforcing our rules.</li>
          <li><strong>To tell you about things you asked for</strong>: notifications, search alerts, waitlist spots,
            and emails or SMS about your tickets and account.</li>
          <li><strong>To meet legal obligations</strong>: tax and accounting records for payments, and responding to
            lawful requests from authorities.</li>
        </ul>
        <p>We don&apos;t sell your personal data, and we don&apos;t use advertising or cross-site tracking.</p>

        <H id="share">Who we share it with</H>
        <ul>
          <li><strong>Organizers</strong>{" "}of events you get tickets for or RSVP to: your name, username and ticket
            details, so they can run the door. Your public profile is visible to everyone.</li>
          <li><strong>Service providers</strong>{" "}that work for us under contract: Paystack (payments), our email
            and SMS providers (including Twilio), our hosting and file storage providers, Google or Instagram if you
            choose to sign in with them, and an AI provider that helps us find and draft public event listings
            (it isn&apos;t sent your account data).</li>
          <li><strong>Maps:</strong>{" "}event pages with a location show an OpenStreetMap map, which loads from
            OpenStreetMap&apos;s servers. &quot;Get directions&quot; opens Google Maps only when you tap it.</li>
          <li><strong>Authorities</strong>, when the law requires it.</li>
        </ul>
        <p>
          Some of these providers process data outside Nigeria. Where they do, we rely on the transfer safeguards
          the NDPA allows, such as adequacy decisions and contractual protections.
        </p>

        <H id="storage">Cookies and storage on your device</H>
        <p>
          Turnup doesn&apos;t use advertising or analytics cookies. We keep a few things in your browser&apos;s or
          app&apos;s storage because Turnup can&apos;t work without them: your sign-in, your theme, and copies of
          your tickets so they open offline at the door. Clearing your browser data removes them and signs you out.
        </p>

        <H id="keep">How long we keep it</H>
        <ul>
          <li>Your account, until you delete it. Deleting your account deactivates it at once and signs you out
            everywhere.</li>
          <li>Payment and order records, for as long as tax and accounting law requires, even after you delete
            your account.</li>
          <li>Your app activity (what you view, search and tap), 180 days, then it&apos;s deleted. The
            record of your data choices is kept while your account exists.</li>
          <li>Search alerts end after 60 days. Hidden events and organizers stay hidden until you unhide them.</li>
          <li>Venue verification documents, only for the retention period set for verification, then they are
            deleted.</li>
        </ul>

        <H id="rights">Your rights</H>
        <p>Under the NDPA you can:</p>
        <ul>
          <li>ask for a copy of the personal data we hold about you;</li>
          <li>have inaccurate data corrected (most of it you can edit yourself in your profile and Settings);</li>
          <li>have your data deleted, or its use restricted;</li>
          <li>receive your data in a portable format;</li>
          <li>object to our use of it, including for recommendations;</li>
          <li>withdraw any consent you gave, without affecting what we did before; and</li>
          <li>complain to the Nigeria Data Protection Commission (NDPC).</li>
        </ul>
        <p>
          You can download a copy of your data, see the history of your data choices, and change them yourself
          in <Link href="/settings" className="text-primary hover:underline">Settings</Link> under &quot;Your data&quot;.
          For anything else, email <a href={`mailto:${CONTACT}`} className="text-primary hover:underline">{CONTACT}</a>{" "}
          from the address on your account. We reply within 30 days.
        </p>

        <H id="security">Security</H>
        <p>
          Connections to Turnup are encrypted, passwords are hashed, two-factor sign-in is available, and sensitive
          files are stored privately and only served through short-lived links. No system is perfectly secure: if a
          breach affects your data, we&apos;ll tell you and the NDPC as the law requires.
        </p>

        <H id="children">Children</H>
        <p>
          Turnup isn&apos;t meant for children under 13, and we don&apos;t knowingly collect their data. If you
          believe a child has an account, contact us and we&apos;ll remove it.
        </p>

        <H id="changes">Changes</H>
        <p>
          When we change this policy we&apos;ll update the date at the top, and tell you in the app about any
          significant change before it takes effect.
        </p>

        <p className="pt-4 text-xs text-text-muted">
          Questions? Email <a href={`mailto:${CONTACT}`} className="text-primary hover:underline">{CONTACT}</a> or
          manage your account in <Link href="/settings" className="text-primary hover:underline">Settings</Link>.
        </p>
      </article>
    </div>
  );
}
