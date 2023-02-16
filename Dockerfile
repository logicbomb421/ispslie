FROM python:3.10-alpine3.17

# TODO: multi-stage and reorder for caching

RUN apk add make gcc g++ linux-headers

WORKDIR /ispslie
COPY . .

RUN pip install .

VOLUME /ispslie
ENTRYPOINT [ "python", "-m" ]
CMD [ "ispslie"]
