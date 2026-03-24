const { sendEmail } = require('./service/emailService');

(async () => {
  try {
    await sendEmail('example@gmail.com', 'Test Email from Brain API', '<h1>Hello from Brain API!</h1>', 'Hello from Brain API!');
    console.log('Test email sent successfully!');
  } catch (error) {
    console.error('Error sending test email:', error);
  }
})();

