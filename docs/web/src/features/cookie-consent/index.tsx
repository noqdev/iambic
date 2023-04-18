import React, { useEffect } from "react";
import ReactCookieConsent from "react-cookie-consent";
import Link from "@docusaurus/Link";
import { translate } from "@docusaurus/Translate";
import Cookies from 'universal-cookie';

export const CookieConsent = () => {
    const cookies = new Cookies();
    const cookieName = "fs-cc";

    useEffect(() => {
        if (cookies.get(cookieName)) {
            pushGTMEvent();
        }
    }, []);

    const pushGTMEvent = () => {
        window.dataLayer = window.dataLayer || [];
        window.dataLayer.push({
            event: "analytics-activated",
        });
    };

    const onAccept = () => {
        pushGTMEvent();
    };

    return (
        <ReactCookieConsent
            location="bottom"
            cookieName="fs-cc"
            onAccept={onAccept}
        >
            {"By clicking “I understand”, you agree to the storing of cookies on your device to enhance site navigation, analyze site usage, and assist in our marketing efforts. View our Privacy Policy for more information." }
            <Link to="https://www.iambic.org/privacy-policy"> (
                {"Privacy Policy"}
                )
            </Link>
        </ReactCookieConsent>
    );
};
