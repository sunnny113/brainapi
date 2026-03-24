require('dotenv').config();
const { TransactionalEmailsApi, BrevoClient } = require('@getbrevo/brevo');

// Configure Brevo Client
const BREVO_API_KEY = process.env.BREVO_API_KEY;
const senderEmail = 'support@brainapi.site';
const senderName = 'Brain API';

if (!BREVO_API_KEY) throw new Error('BREVO_API_KEY is not set in environment variables');

const brevoClient = new BrevoClient(BREVO_API_KEY);
const transactionalEmailsApi = new TransactionalEmailsApi(brevoClient);

/**
 * Send email using Brevo transactional email service
 * @param {string} to - Recipient email address
 * @param {string} subject - Subject of the email
 * @param {string} htmlContent - HTML content of the email
 * @param {string} [textContent] - Optional plain text content of the email
 * @returns {Promise<void>}
 */
async function sendEmail(to, subject, htmlContent, textContent) {
    try {
        const sendSmtpEmail = new transactionalEmailsApi.SendSmtpEmail({
            sender: { email: senderEmail, name: senderName },
            to: [{ email: to }],
            subject,
            htmlContent,
            textContent,
        });

        await transactionalEmailsApi.sendTransacEmail(sendSmtpEmail);
        console.log(`Email sent successfully to ${to}`);
    } catch (error) {
        console.error(`Failed to send email: ${error.message}`);
    }
}

module.exports = { sendEmail };
