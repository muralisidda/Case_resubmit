import javax.jms.*;
import com.tibco.tibjms.*;

/**
 * EmsProducer – sends a workflowMessageRequest to a TIBCO EMS queue
 * and waits for the synchronous workflowMessageResponse reply.
 *
 * Usage:
 *   java -cp tibjms.jar;javax.jms-api.jar;. EmsProducer
 *        <host> <port> <username> <password> <queue> <messageXml>
 *
 * On success  : prints the reply XML body to stdout, exits 0.
 * On timeout  : prints error to stderr, exits 2.
 * On error    : prints error to stderr, exits 1.
 */
public class EmsProducer {

    private static final int REPLY_TIMEOUT_MS = 30000;

    public static void main(String[] args) throws Exception {
        if (args.length < 6) {
            System.err.println("Usage: EmsProducer <host> <port> <username> <password> <queue> <messageXml>");
            System.exit(1);
        }

        String host       = args[0];
        int    port       = Integer.parseInt(args[1]);
        String username   = args[2];
        String password   = args[3];
        String queueName  = args[4];
        String messageXml = args[5];

        String url = "tcp://" + host + ":" + port;

        TibjmsConnectionFactory factory = new TibjmsConnectionFactory(url);
        Connection connection = null;

        try {
            connection = factory.createConnection(username, password);
            connection.start();

            Session session = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);

            Queue         requestQueue = session.createQueue(queueName);
            TemporaryQueue replyQueue  = session.createTemporaryQueue();

            MessageProducer producer = session.createProducer(requestQueue);
            producer.setDeliveryMode(DeliveryMode.NON_PERSISTENT);

            MessageConsumer consumer = session.createConsumer(replyQueue);

            TextMessage request = session.createTextMessage(messageXml);
            request.setStringProperty("Content-Type", "text/xml;charset=utf-8");
            request.setJMSReplyTo(replyQueue);

            producer.send(request);

            // Wait for synchronous reply
            Message reply = consumer.receive(REPLY_TIMEOUT_MS);
            if (reply == null) {
                System.err.println("Timeout: no reply received within " + (REPLY_TIMEOUT_MS / 1000) + " seconds.");
                System.exit(2);
            }

            if (reply instanceof TextMessage) {
                System.out.println(((TextMessage) reply).getText());
            } else {
                System.out.println("<replyReceived/>");
            }

        } finally {
            if (connection != null) {
                try { connection.close(); } catch (Exception ignored) {}
            }
        }
    }
}
